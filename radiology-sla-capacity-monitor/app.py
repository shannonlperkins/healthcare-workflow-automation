from pathlib import Path

import pandas as pd
import streamlit as st

from risk_engine import score_queue, summarize_queue
from demo_history import generate_history
from forecast_engine import DEMO_NOW, forecast_demand, project_capacity, backtest_forecast

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

st.set_page_config(
    page_title="Radiology SLA & Capacity Risk Monitor",
    page_icon="📡",
    layout="wide",
)

st.title("Radiology SLA & Capacity Risk Monitor")
st.caption(
    "Portfolio prototype · synthetic data only · Phase 1 queue monitoring + Phase 2 demand forecasting. "
    "Automate surveillance; preserve human judgment."
)


@st.cache_data
def load_data():
    clients = pd.read_csv(DATA_DIR / "clients.csv")
    radiologists = pd.read_csv(DATA_DIR / "radiologists.csv")
    studies = pd.read_csv(DATA_DIR / "studies.csv")
    return clients, radiologists, studies


clients, radiologists, studies = load_data()

studies = studies.merge(
    clients[
        [
            "client",
            "sla_stat_minutes",
            "sla_urgent_minutes",
            "sla_routine_minutes",
        ]
    ],
    on="client",
    how="left",
)


def sla_for_row(row):
    if row["priority"] == "STAT":
        return row["sla_stat_minutes"]
    if row["priority"] == "Urgent":
        return row["sla_urgent_minutes"]
    return row["sla_routine_minutes"]


studies["sla_minutes"] = studies.apply(sla_for_row, axis=1)

scored = score_queue(studies, radiologists)
summary = summarize_queue(scored)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Open studies", summary["total_studies"])
c2.metric("Red risk", summary["red"])
c3.metric("Yellow risk", summary["yellow"])
c4.metric("SLA breached", summary["sla_breached"])
c5.metric("No eligible reader", summary["no_eligible_reader"])

def render_current_queue():
    st.subheader("Priority queue")
    bands = st.multiselect(
        "Risk band",
        options=["RED", "YELLOW", "GREEN"],
        default=["RED", "YELLOW", "GREEN"],
    )
    filtered = scored[scored["risk_band"].isin(bands)].copy()

    st.dataframe(
        filtered[
            [
                "study_id",
                "client",
                "priority",
                "modality",
                "age_minutes",
                "sla_minutes",
                "minutes_to_sla",
                "eligible_radiologists",
                "risk_score",
                "risk_band",
                "recommended_action",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Ambassador action list")
    actionable = scored[scored["risk_band"].isin(["RED", "YELLOW"])].head(10)
    if actionable.empty:
        st.success("No studies currently require ambassador intervention.")
    else:
        for _, row in actionable.iterrows():
            st.markdown(
                f"**{row['risk_band']} — {row['study_id']} | {row['client']} | "
                f"{row['modality']} | {row['priority']}**  \n"
                f"Risk **{row['risk_score']}** · {row['minutes_to_sla']} min to SLA · "
                f"{row['eligible_radiologists']} eligible reader(s)  \n"
                f"**Next action:** {row['recommended_action']}"
            )

    st.subheader("Capacity view")
    capacity = radiologists.copy()
    capacity["utilization_pct"] = (
        capacity["current_workload"] / capacity["max_workload"] * 100
    ).round(0)
    capacity["available_slots"] = (
        capacity["max_workload"] - capacity["current_workload"]
    ).clip(lower=0)

    st.dataframe(
        capacity[
            [
                "radiologist",
                "active",
                "modalities",
                "current_workload",
                "max_workload",
                "available_slots",
                "utilization_pct",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


@st.cache_data
def historical_demo():
    return generate_history()


@st.cache_data
def forecast_validation():
    return backtest_forecast(historical_demo(), DEMO_NOW)


@st.cache_data
def run_projection(hours, simulations, surge=0, unavailable=(), activate=()):
    history = historical_demo()
    forecast = forecast_demand(history, DEMO_NOW, hours, 1 + surge / 100)
    shifts = pd.read_csv(DATA_DIR / "shifts.csv")
    projection = project_capacity(forecast, clients, studies, radiologists, shifts,
                                  DEMO_NOW, hours, simulations, seed=42,
                                  unavailable=unavailable, activate=activate)
    return forecast.drop(columns="samples"), projection


def render_forecast():
    st.subheader("Plan coverage before the backlog builds")
    st.caption("Fixed demo snapshot: October 6, 2026, 5:00 PM America/Chicago (22:00 UTC). "
               "The model learns from 56 days of invented hourly counts; these are not employer results.")
    with st.form("forecast_controls"):
        c1, c2, c3 = st.columns(3)
        hours = c1.slider("Forecast horizon (hours)", 2, 12, 6)
        simulations = c2.selectbox("Demand scenarios", [50, 100, 200], index=1)
        surge = c3.slider("Scenario: volume change (%)", -50, 100, 0, step=10)
        c4, c5 = st.columns(2)
        unavailable = c4.multiselect("Scenario: remove reader coverage", radiologists.radiologist.tolist())
        activate = c5.multiselect("Scenario: cover full window with existing reader",
                                 radiologists.radiologist.tolist(), help="Hypothetical shift override only; "
                                 "client and modality credentials still apply. No new credentials are assumed.")
        st.form_submit_button("Compare coverage scenarios")
    if set(unavailable) & set(activate):
        st.error("Choose separate readers to remove and activate.")
        return
    with st.spinner("Forecasting hourly demand and testing shared reader capacity…"):
        forecast, baseline = run_projection(hours, simulations)
        scenario_forecast, scenario = run_projection(hours, simulations, surge,
                                                       tuple(sorted(unavailable)), tuple(sorted(activate)))
    changed = surge != 0 or bool(unavailable) or bool(activate)
    selected = scenario if changed else baseline
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected new studies", selected.totals["expected_arrivals"])
    c2.metric("Expected completed studies", selected.totals["expected_completions"])
    c3.metric("Expected SLA misses", selected.totals["expected_sla_misses"])
    c4.metric("Expected end backlog", selected.totals["expected_end_backlog"])
    st.caption("Completions include the initial open queue. SLA misses count studies due within this window, "
               "including already overdue studies. Backlog includes studies whose routine SLAs extend beyond the window.")

    st.markdown("**Demand and throughput by hour**")
    display = selected.hourly.copy()
    display["hour_start"] = display.hour_start.dt.tz_convert("America/Chicago")
    st.line_chart(display.set_index("hour_start")[["expected_arrivals", "expected_completions", "expected_backlog"]])
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption("Read minutes compare modality-specific demand with unique scheduled reader minutes, adjusted "
               "for modeled speed and initial busy time. An aggregate surplus can still hide credentialing gaps.")

    st.markdown("**Client and modality exceptions**")
    st.dataframe(selected.risks, use_container_width=True, hide_index=True)
    st.caption(f"Simulated breach % = share of {simulations} demand scenarios with at least one due study "
               "missing its SLA in this client / modality / priority group. It is not a per-study probability "
               "or a calibrated real-world estimate. Operational priority comes from existing classifications.")
    exceptions = selected.risks[(selected.risks.simulated_breach_pct >= 20)
                               | (selected.risks.eligible_scheduled_readers == 0)].head(5)
    for row in exceptions.to_dict("records"):
        st.markdown(f"**{row['risk_band']} · {row['client']} · {row['modality']} / {row['priority']}** — "
                    f"{row['simulated_breach_pct']:.0f}% simulated breach frequency, "
                    f"{row['expected_sla_misses']:.1f} expected misses. {row['recommended_action']}")

    st.markdown("**Coverage scenario comparison**")
    comparison = pd.DataFrame([
        {"metric": label, "baseline": baseline.totals[key], "scenario": scenario.totals[key],
         "change": round(scenario.totals[key] - baseline.totals[key], 1)}
        for key, label in [("expected_arrivals", "New studies"),
                           ("expected_completions", "Completed studies"),
                           ("expected_sla_misses", "SLA misses"),
                           ("expected_end_backlog", "End backlog")]])
    st.dataframe(comparison, use_container_width=True, hide_index=True)
    if changed:
        improvement = baseline.totals["expected_sla_misses"] - scenario.totals["expected_sla_misses"]
        st.info(f"This scenario changes expected SLA misses by {-improvement:+.1f} over {hours} hours. "
                "Use the client-level view to check who benefits; this is a coverage discussion aid.")
    st.download_button("Download client risk projection", selected.risks.to_csv(index=False),
                       file_name="synthetic_client_risk_projection.csv", mime="text/csv")
    st.download_button("Download hourly capacity projection", display.to_csv(index=False),
                       file_name="synthetic_hourly_capacity_projection.csv", mime="text/csv")

    with st.expander("Forecast evidence and assumptions"):
        results = forecast_validation()
        st.write(f"Rolling holdout check: {results['holdout_cells']} stream/hour predictions across "
                 f"the last 7 synthetic days (one holdout every 4 hours). Mean absolute error: "
                 f"{results['mae_studies']} studies per stream/hour; weighted absolute percentage error: "
                 f"{results['wape_pct']}%. Flat recent-week baseline MAE: {results['flat_baseline_mae']}.")
        st.dataframe(scenario_forecast if changed else forecast, use_container_width=True, hide_index=True)
        st.write("The model samples completed historical hours with matching weekday and hour. "
                 "Sparse history falls back to the same hour, then the whole observed window. "
                 "The 10th–90th percentiles describe historical variation, not confidence bounds on the mean.")
        st.write("Each reader can perform one study at a time across all client queues. "
                 "Dispatch uses STAT, then Urgent, then Routine with earliest deadlines inside each class. "
                 "Initial busy minutes are work outside the displayed open queue, avoiding double counting. "
                 "Read duration is a synthetic fixed modality assumption. Shift-end spillover is disallowed.")
        st.write("Production work still needs licensing, privileges, specialty, protocol and report-type rules, "
                 "feed freshness checks, historical read-time distributions, correlated demand modeling, "
                 "and externally validated prediction quality. No studies are actually routed by this demo.")


current_tab, forecast_tab = st.tabs(["Current queue", "Forecast & what-if planning"])
with current_tab:
    render_current_queue()
with forecast_tab:
    try:
        render_forecast()
    except ValueError as error:
        st.error(f"Projection unavailable: {error}")

