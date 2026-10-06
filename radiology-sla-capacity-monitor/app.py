from pathlib import Path

import pandas as pd
import streamlit as st

from risk_engine import score_queue, summarize_queue

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

st.set_page_config(
    page_title="Radiology SLA & Capacity Risk Monitor",
    page_icon="📡",
    layout="wide",
)

st.title("Radiology SLA & Capacity Risk Monitor")
st.caption(
    "Synthetic-data MVP: prioritizes operational risk using SLA age, radiologist eligibility, "
    "queue pressure, and client requirements. It does not interpret images or make clinical decisions."
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

st.info(
    "Production roadmap: replace synthetic inputs with operational feeds, add historical "
    "volume forecasting and calibrated breach prediction, preserve deterministic client/SLA "
    "rules, and keep PHI out of the monitoring layer wherever possible."
)
