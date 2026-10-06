"""Seasonal empirical forecasts and a shared-resource operations simulator.

Only synthetic operational data is supported by the demo. Risk is a frequency
under bootstrap demand scenarios, not a calibrated clinical/contractual model.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

KEYS = ["client", "modality", "priority"]
PRIORITIES = {"STAT": 0, "Urgent": 1, "Routine": 2}
READ_MINUTES = {"CT": 7.0, "MRI": 12.0, "XR": 3.0, "US": 8.0}
SLA_COLUMNS = {"STAT": "sla_stat_minutes", "Urgent": "sla_urgent_minutes",
               "Routine": "sla_routine_minutes"}
DEMO_NOW = pd.Timestamp("2026-10-06T22:00:00Z")


@dataclass
class Projection:
    hourly: pd.DataFrame
    risks: pd.DataFrame
    totals: dict


def _require(frame, columns, name, allow_empty=False):
    missing = set(columns) - set(frame.columns)
    if missing or (frame.empty and not allow_empty):
        raise ValueError(f"{name}: missing columns {sorted(missing)} or empty input")


def forecast_demand(history, now, hours=6, demand_multiplier=1.0):
    """Learn means from completed hourly observations, including observed zeros.

    Each stream must explicitly record every hour in its observation window.
    Missing hours are unknown, never silently imputed as zero.
    """
    _require(history, ["hour_start", *KEYS, "arrivals"], "history")
    now = pd.Timestamp(now)
    if now.tzinfo is None or now != now.floor("h"):
        raise ValueError("Forecast start must be a timezone-aware hour boundary")
    if not 1 <= hours <= 24 or not 0 <= demand_multiplier <= 5:
        raise ValueError("Invalid forecast horizon or demand multiplier")
    data = history.copy()
    data["hour_start"] = pd.to_datetime(data.hour_start, utc=True, errors="raise")
    data["arrivals"] = pd.to_numeric(data.arrivals, errors="raise")
    if (data[KEYS].isna().any().any() or not data.priority.isin(PRIORITIES).all()
            or not data.modality.isin(READ_MINUTES).all()
            or not np.isfinite(data.arrivals).all() or (data.arrivals < 0).any()
            or (data.arrivals % 1 != 0).any()
            or (data.hour_start != data.hour_start.dt.floor("h")).any()
            or data.duplicated(["hour_start", *KEYS]).any()):
        raise ValueError("History must contain unique, hourly, nonnegative integer counts and known streams")
    # Exclude the current incomplete bucket and all future observations.
    data = data[data.hour_start + pd.Timedelta(hours=1) <= now].copy()
    rows = []
    for key, group in data.groupby(KEYS):
        span = pd.date_range(group.hour_start.min(), now - pd.Timedelta(hours=1), freq="h")
        if len(group) != len(span):
            raise ValueError(f"Missing historical hours for {key}; supply zero-count observations explicitly")
        if len(group) < 24:
            raise ValueError(f"Insufficient history for {key}: need at least 24 completed hours")
        for hour in pd.date_range(now, periods=hours, freq="h"):
            same_hour = group[group.hour_start.dt.hour == hour.hour]
            samples = same_hour[same_hour.hour_start.dt.dayofweek == hour.dayofweek]
            basis = "same weekday + hour"
            if len(samples) < 4:
                samples, basis = same_hour, "same hour (weekday fallback)"
                if len(samples) < 7:
                    samples, basis = group, "all hours (sparse-history fallback)"
            values = samples.arrivals.to_numpy(float) * demand_multiplier
            rows.append(dict(zip(KEYS, key)) | {
                "hour_start": hour, "expected_studies": float(values.mean()),
                "p10_studies": float(np.quantile(values, .1)),
                "p90_studies": float(np.quantile(values, .9)),
                "sample_hours": len(values), "forecast_basis": basis,
                "samples": values,
            })
    if not rows:
        raise ValueError("No completed history available before forecast start")
    return pd.DataFrame(rows)


def prepare_readers(readers, shifts, now, hours, unavailable=(), activate=()):
    """Join one explicit shift window per reader. Busy minutes exclude open studies."""
    _require(readers, ["radiologist", "modalities", "credentialed_clients"], "readers")
    _require(shifts, ["radiologist", "shift_start", "shift_end", "busy_minutes", "speed_factor"], "shifts")
    if readers.radiologist.duplicated().any() or shifts.radiologist.duplicated().any():
        raise ValueError("One reader and one shift row per radiologist required")
    if set(readers.radiologist) != set(shifts.radiologist):
        raise ValueError("Every reader needs an explicit shift; unknown readers are rejected")
    if ((set(unavailable) | set(activate)) - set(readers.radiologist)
            or set(unavailable) & set(activate)):
        raise ValueError("Unknown or conflicting scenario reader overrides")
    data = readers.merge(shifts, on="radiologist", validate="one_to_one")
    horizon = hours * 60
    result = []
    for row in data.to_dict("records"):
        start, end = pd.Timestamp(row["shift_start"]), pd.Timestamp(row["shift_end"])
        busy, speed = float(row["busy_minutes"]), float(row["speed_factor"])
        if (start.tzinfo is None or end.tzinfo is None or end <= start
                or not math.isfinite(busy) or busy < 0
                or not math.isfinite(speed) or speed <= 0):
            raise ValueError("Invalid shift, busy minutes, or reader speed")
        name = row["radiologist"]
        a = max(0., (start - now).total_seconds() / 60)
        b = min(float(horizon), (end - now).total_seconds() / 60)
        if name in activate:
            a, b = 0., float(horizon)  # explicit hypothetical coverage override
        if name in unavailable:
            b = a
        result.append({"name": name, "start": a, "end": b,
                       "free": a + busy, "speed": speed,
                       "clients": set(str(row["credentialed_clients"]).split(";")),
                       "modalities": set(str(row["modalities"]).split(";"))})
    return result


def _eligible(job, reader):
    return job["client"] in reader["clients"] and job["modality"] in reader["modalities"]


def simulate_queue(jobs, readers, horizon_minutes):
    """Nonpreemptive service with approved priority order then earliest deadline.

    A reader serves one job at a time across ALL clients/modalities. A study
    cannot finish outside that reader's shift or start before its arrival.
    Ineligible jobs remain visible as unserved. Dispatch is hypothetical only.
    """
    waiting = sorted([dict(j) for j in jobs], key=lambda j: j["arrival"])
    workers = [dict(r) for r in readers]
    finished = []
    t = 0.
    while t < horizon_minutes and waiting:
        ready = sorted([j for j in waiting if j["arrival"] <= t],
                       key=lambda j: (PRIORITIES[j["priority"]], j["deadline"], j["arrival"], j["id"]))
        for job in ready:
            candidates = [r for r in workers if r["start"] <= t and r["free"] <= t
                          and _eligible(job, r)
                          and t + job["read_minutes"] / r["speed"] <= r["end"]
                          and t + job["read_minutes"] / r["speed"] <= horizon_minutes]
            if not candidates:
                continue
            # Prefer the least flexible eligible reader to protect scarce capacity.
            reader = min(candidates, key=lambda r: (len(r["clients"]) * len(r["modalities"]),
                                                   -r["speed"], r["name"]))
            completion = t + job["read_minutes"] / reader["speed"]
            reader["free"] = completion
            finished.append(job | {"completion": completion, "reader": reader["name"]})
            waiting.remove(job)
        events = [j["arrival"] for j in waiting if t < j["arrival"] < horizon_minutes]
        events += [max(r["free"], r["start"]) for r in workers
                   if t < max(r["free"], r["start"]) < min(r["end"], horizon_minutes)]
        if not events:
            break
        t = min(events)
    return finished, waiting


def project_capacity(forecast, clients, studies, readers, shifts, now, hours=6,
                     simulations=100, seed=42, unavailable=(), activate=()):
    """Run repeatable empirical demand scenarios and summarize due-within-window misses."""
    if not 10 <= simulations <= 1000:
        raise ValueError("Use 10–1000 simulations")
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware forecast start required")
    _require(clients, ["client", *SLA_COLUMNS.values()], "clients")
    _require(studies, ["study_id", *KEYS, "age_minutes"], "studies", allow_empty=True)
    _require(forecast, ["hour_start", *KEYS, "samples"], "forecast")
    if forecast.duplicated(["hour_start", *KEYS]).any():
        raise ValueError("Duplicate forecast stream/hour")
    for samples in forecast.samples:
        samples = np.asarray(samples, dtype=float)
        if samples.size == 0 or not np.isfinite(samples).all() or (samples < 0).any():
            raise ValueError("Invalid forecast demand samples")
    if clients.client.duplicated().any() or studies.study_id.duplicated().any():
        raise ValueError("Duplicate client rules or study IDs")
    values = clients[list(SLA_COLUMNS.values())].to_numpy(float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Positive, finite SLA rules required")
    sla = clients.set_index("client").to_dict("index")
    horizon = hours * 60
    workers = prepare_readers(readers, shifts, now, hours, unavailable, activate)
    groups = {tuple(r[k] for k in KEYS) for r in forecast.to_dict("records")}
    groups |= {tuple(r[k] for k in KEYS) for r in studies.to_dict("records")}
    for client, modality, priority in groups:
        if client not in sla or modality not in READ_MINUTES or priority not in SLA_COLUMNS:
            raise ValueError("Unknown client, modality, or priority; explicit operational rules required")
    initial = []
    for row in studies.to_dict("records"):
        age = float(row["age_minutes"])
        if not math.isfinite(age) or age < 0:
            raise ValueError("Nonnegative finite study ages required")
        initial.append({"id": row["study_id"], "is_initial": True, **{k: row[k] for k in KEYS},
                        "arrival": -age, "deadline": sla[row["client"]][SLA_COLUMNS[row["priority"]]] - age,
                        "read_minutes": READ_MINUTES[row["modality"]]})
    rng = np.random.default_rng(seed)
    accum = {key: {"breach_runs": 0, "misses": 0, "arrivals": 0, "pending": 0} for key in groups}
    hourly_counts = np.zeros((simulations, hours, 4))  # arrivals, completions, backlog, read demand minutes
    total_misses, total_pending = [], []
    for run in range(simulations):
        jobs = [dict(j) for j in initial]
        for i, row in enumerate(forecast.to_dict("records")):
            offset = int((row["hour_start"] - now).total_seconds() // 3600)
            if not 0 <= offset < hours:
                raise ValueError("Forecast hour outside simulation horizon")
            sample = float(rng.choice(row["samples"]))
            # Stochastic rounding preserves the expectation for fractional scenario multipliers.
            count = int(np.floor(sample)) + int(rng.random() < sample % 1)
            for j in range(count):
                arrival = offset * 60 + float(rng.uniform(0, 60))
                jobs.append({"id": f"F-{i}-{j}", **{k: row[k] for k in KEYS},
                             "arrival": arrival,
                             "deadline": arrival + sla[row["client"]][SLA_COLUMNS[row["priority"]]],
                             "read_minutes": READ_MINUTES[row["modality"]]})
        done, pending = simulate_queue(jobs, workers, horizon)
        missed = [j for j in done if j["deadline"] <= horizon and j["completion"] > j["deadline"]]
        missed += [j for j in pending if j["deadline"] <= horizon]
        total_misses.append(len(missed))
        total_pending.append(len(pending))
        for key, stats in accum.items():
            match = lambda j: tuple(j[k] for k in KEYS) == key
            misses = sum(match(j) for j in missed)
            stats["breach_runs"] += int(misses > 0)
            stats["misses"] += misses
            stats["arrivals"] += sum(match(j) and not j.get("is_initial", False) for j in jobs)
            stats["pending"] += sum(match(j) for j in pending)
        for h in range(hours):
            a, b = h * 60, (h + 1) * 60
            arriving = [j for j in jobs if not j.get("is_initial", False) and a <= j["arrival"] < b]
            hourly_counts[run, h] = [len(arriving),
                sum(a < j["completion"] <= b for j in done),
                sum(j["arrival"] < b for j in jobs) - sum(j["completion"] <= b for j in done),
                sum(j["read_minutes"] for j in arriving)]
    risks = []
    for key, stats in accum.items():
        example = dict(zip(KEYS, key))
        eligible = [r for r in workers if _eligible(example, r) and r["end"] > r["free"]]
        p = stats["breach_runs"] / simulations
        label = "HIGH" if p >= .5 else "WATCH" if p >= .2 else "LOW"
        if not eligible:
            action = "Coverage gap: review credentialed modality coverage; additional general capacity cannot solve this."
        elif p >= .2:
            action = "Review eligible coverage and shift overlap; compare a reserve-reader scenario before escalation."
        else:
            action = "Continue monitoring; no forecast-driven coverage escalation."
        risks.append(example | {"simulated_breach_pct": round(p * 100, 1),
                     "risk_band": label, "expected_new_studies": round(stats["arrivals"] / simulations, 1),
                     "expected_sla_misses": round(stats["misses"] / simulations, 1),
                     "expected_end_backlog": round(stats["pending"] / simulations, 1),
                     "eligible_scheduled_readers": len(eligible), "recommended_action": action})
    hourly = []
    for h in range(hours):
        a, b = h * 60, (h + 1) * 60
        capacity = sum(max(0, min(b, r["end"]) - max(a, r["free"], r["start"])) * r["speed"]
                       for r in workers)
        mean = hourly_counts[:, h].mean(axis=0)
        hourly.append({"hour_start": now + pd.Timedelta(hours=h),
                       "expected_arrivals": round(mean[0], 1),
                       "arrivals_p10": float(np.quantile(hourly_counts[:, h, 0], .1)),
                       "arrivals_p90": float(np.quantile(hourly_counts[:, h, 0], .9)),
                       "expected_completions": round(mean[1], 1),
                       "expected_backlog": round(mean[2], 1),
                       "demand_read_minutes": round(mean[3], 1),
                       "available_read_minutes": round(capacity, 1),
                       "aggregate_gap_minutes": round(max(0, mean[3] - capacity), 1)})
    return Projection(pd.DataFrame(hourly), pd.DataFrame(risks).sort_values(
        ["simulated_breach_pct", "expected_sla_misses"], ascending=False).reset_index(drop=True),
        {"expected_arrivals": round(float(hourly_counts[:, :, 0].sum(axis=1).mean()), 1),
         "expected_completions": round(float(hourly_counts[:, :, 1].sum(axis=1).mean()), 1),
         "expected_sla_misses": round(float(np.mean(total_misses)), 1),
         "expected_end_backlog": round(float(np.mean(total_pending)), 1),
         "any_breach_pct": round(float(np.mean(np.array(total_misses) > 0) * 100), 1),
         "simulations": simulations})


def backtest_forecast(history, now, days=7):
    """Rolling one-hour holdouts; training ends before each tested hour."""
    data = history.copy()
    data["hour_start"] = pd.to_datetime(data.hour_start, utc=True)
    # Six spaced holdouts per day keeps an interactive demo fast.
    errors, actuals, baseline_errors = [], [], []
    for hour in pd.date_range(now - pd.Timedelta(days=days), now - pd.Timedelta(hours=1), freq="4h"):
        predicted = forecast_demand(data, hour, hours=1)
        observed = data[data.hour_start == hour]
        comparison = predicted.merge(observed, on=["hour_start", *KEYS], validate="one_to_one")
        if len(comparison) != len(predicted):
            raise ValueError("Missing holdout observations")
        for row in comparison.to_dict("records"):
            errors.append(abs(row["expected_studies"] - row["arrivals"]))
            actuals.append(row["arrivals"])
            recent = data[(data.hour_start < hour) & (data.hour_start >= hour - pd.Timedelta(days=7))]
            for k in KEYS:
                recent = recent[recent[k] == row[k]]
            baseline_errors.append(abs(float(recent.arrivals.mean()) - row["arrivals"]))
    total = sum(actuals)
    return {"holdout_cells": len(errors), "mae_studies": round(float(np.mean(errors)), 2),
            "wape_pct": round(sum(errors) / total * 100, 1) if total else None,
            "flat_baseline_mae": round(float(np.mean(baseline_errors)), 2)}
