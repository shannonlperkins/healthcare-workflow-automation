from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from demo_history import generate_history
from forecast_engine import (DEMO_NOW, READ_MINUTES, forecast_demand, project_capacity,
                             simulate_queue, backtest_forecast, prepare_readers)


def history(days=28, count=2):
    return pd.DataFrame([{"hour_start": h, "client": "X", "modality": "CT",
                          "priority": "STAT", "arrivals": count}
                         for h in pd.date_range(DEMO_NOW - pd.Timedelta(days=days),
                                                DEMO_NOW - pd.Timedelta(hours=1), freq="h")])


def worker(name="R", clients=("X", "Y"), modalities=("CT",), start=0, end=60, free=0):
    return {"name": name, "clients": set(clients), "modalities": set(modalities),
            "start": start, "end": end, "free": free, "speed": 1.0}


def job(identifier, client="X", modality="CT", arrival=0, priority="STAT", deadline=30):
    return {"id": identifier, "client": client, "modality": modality, "priority": priority,
            "arrival": arrival, "deadline": deadline, "read_minutes": READ_MINUTES[modality]}


def inputs():
    clients = pd.DataFrame([{"client": "X", "sla_stat_minutes": 10,
                             "sla_urgent_minutes": 60, "sla_routine_minutes": 480}])
    studies = pd.DataFrame([{"study_id": "A", "client": "X", "modality": "CT",
                             "priority": "STAT", "age_minutes": 0}])
    readers = pd.DataFrame([{"radiologist": "R", "credentialed_clients": "X", "modalities": "CT"}])
    shifts = pd.DataFrame([{"radiologist": "R", "shift_start": DEMO_NOW,
                            "shift_end": DEMO_NOW + pd.Timedelta(hours=1),
                            "busy_minutes": 0, "speed_factor": 1}])
    return clients, studies, readers, shifts


def test_learns_weekday_hour_without_future_leakage():
    data = history()
    mask = ((data.hour_start.dt.dayofweek == DEMO_NOW.dayofweek)
            & (data.hour_start.dt.hour == DEMO_NOW.hour))
    data.loc[mask, "arrivals"] = 9
    future = data.iloc[:1].copy()
    future["hour_start"], future["arrivals"] = DEMO_NOW, 10000
    result = forecast_demand(pd.concat([data, future]), DEMO_NOW, hours=1).iloc[0]
    assert result.expected_studies == 9
    assert result.sample_hours == 4
    assert result.forecast_basis == "same weekday + hour"


def test_observed_zeros_and_volume_multiplier():
    assert forecast_demand(history(count=0), DEMO_NOW, 1).iloc[0].expected_studies == 0
    assert forecast_demand(history(count=2), DEMO_NOW, 1, 1.5).iloc[0].expected_studies == 3


@pytest.mark.parametrize("days,basis", [(7, "same hour (weekday fallback)"),
                                       (1, "all hours (sparse-history fallback)")])
def test_sparse_history_reports_fallback(days, basis):
    assert forecast_demand(history(days), DEMO_NOW, 1).iloc[0].forecast_basis == basis


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "negative", "fractional", "nan", "gap_at_end"])
def test_invalid_history_fails_visibly(mutation):
    data = history()
    if mutation == "missing":
        data = data.drop(index=10)
    elif mutation == "gap_at_end":
        data = data.iloc[:-1]
    elif mutation == "duplicate":
        data = pd.concat([data, data.iloc[:1]])
    else:
        data["arrivals"] = data.arrivals.astype(float)
        data.loc[0, "arrivals"] = {"negative": -1, "fractional": .5, "nan": np.nan}[mutation]
    with pytest.raises(ValueError):
        forecast_demand(data, DEMO_NOW, 1)


def test_shared_reader_capacity_not_multiplied_by_client_count():
    done, pending = simulate_queue([job("A"), job("B", client="Y")], [worker(end=10)], 60)
    assert len(done) == 1
    assert len(pending) == 1
    assert done[0]["completion"] == 7


def test_shift_start_and_busy_time_delay_service():
    done, _ = simulate_queue([job("A")], [worker(start=10, free=15)], 60)
    assert done[0]["completion"] == 22


def test_no_reading_after_shift_end_or_for_ineligible_modality():
    jobs = [job("A"), job("B", modality="MRI")]
    done, pending = simulate_queue(jobs, [worker(end=6)], 60)
    assert not done
    assert len(pending) == 2


def test_priority_then_deadline_and_nonpreemption():
    jobs = [job("routine", priority="Routine", deadline=5),
            job("stat2", deadline=20), job("stat1", deadline=10),
            job("future", arrival=1, deadline=2)]
    done, _ = simulate_queue(jobs, [worker()], 60)
    assert [j["id"] for j in done] == ["stat1", "future", "stat2", "routine"]
    assert done[1]["completion"] == 14


def test_projection_conserves_queue_and_is_reproducible():
    f = forecast_demand(history(count=3), DEMO_NOW, 1)
    r = project_capacity(f, *inputs(), DEMO_NOW, hours=1, simulations=20)
    r2 = project_capacity(f, *inputs(), DEMO_NOW, hours=1, simulations=20)
    pd.testing.assert_frame_equal(r.hourly, r2.hourly)
    assert r.totals["expected_arrivals"] + 1 == pytest.approx(
        r.totals["expected_completions"] + r.totals["expected_end_backlog"], abs=.11)
    assert r.hourly.available_read_minutes.sum() == 60


def test_no_coverage_and_deadlines_beyond_horizon():
    f = forecast_demand(history(count=0), DEMO_NOW, 1)
    a = inputs()
    result = project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10, unavailable=("R",))
    assert result.totals["expected_sla_misses"] == 1
    assert result.risks.iloc[0].simulated_breach_pct == 100
    a[1].loc[0, "priority"] = "Routine"
    routine = project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10, unavailable=("R",))
    assert routine.totals["expected_sla_misses"] == 0
    assert routine.totals["expected_end_backlog"] == 1


def test_activating_reader_preserves_credentials():
    f = forecast_demand(history(count=0), DEMO_NOW, 1)
    a = inputs()
    a[2].loc[0, "credentialed_clients"] = "Different client"
    result = project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10, activate=("R",))
    assert result.totals["expected_completions"] == 0
    assert result.risks.iloc[0].eligible_scheduled_readers == 0


@pytest.mark.parametrize("problem", ["unknown_client", "negative_age", "bad_speed", "missing_shift"])
def test_projection_rejects_invalid_rules(problem):
    f = forecast_demand(history(count=0), DEMO_NOW, 1)
    a = inputs()
    if problem == "unknown_client":
        a[1].loc[0, "client"] = "Unknown"
    elif problem == "negative_age":
        a[1].loc[0, "age_minutes"] = -2
    elif problem == "bad_speed":
        a[3].loc[0, "speed_factor"] = 0
    else:
        a[3].loc[0, "radiologist"] = "Other"
    with pytest.raises(ValueError):
        project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10)


def test_reserve_coverage_improves_synthetic_demo():
    root = Path(__file__).resolve().parents[1] / "data"
    a = [pd.read_csv(root / f"{name}.csv") for name in ("clients", "studies", "radiologists", "shifts")]
    f = forecast_demand(generate_history(), DEMO_NOW, 6)
    base = project_capacity(f, *a, DEMO_NOW, simulations=20)
    scenario = project_capacity(f, *a, DEMO_NOW, simulations=20, activate=("Dr. Brooks",))
    assert scenario.totals["expected_sla_misses"] < base.totals["expected_sla_misses"]
    assert scenario.totals["expected_completions"] > base.totals["expected_completions"]
    assert scenario.totals["expected_arrivals"] == base.totals["expected_arrivals"]


def test_backtest_constant_history_has_zero_error():
    result = backtest_forecast(history(days=35), DEMO_NOW, days=1)
    assert result["mae_studies"] == 0
    assert result["wape_pct"] == 0
    assert result["flat_baseline_mae"] == 0


def test_empty_open_queue_and_conflicting_override():
    f = forecast_demand(history(count=0), DEMO_NOW, 1)
    a = list(inputs())
    a[1] = a[1].iloc[:0]
    result = project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10)
    assert result.totals["expected_arrivals"] == 0
    assert result.totals["expected_sla_misses"] == 0
    with pytest.raises(ValueError, match="conflicting"):
        project_capacity(f, *a, DEMO_NOW, hours=1, simulations=10, unavailable=("R",), activate=("R",))
