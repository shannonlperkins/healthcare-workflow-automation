from __future__ import annotations

import pandas as pd

PRIORITY_WEIGHT = {
    "STAT": 1.0,
    "Urgent": 0.65,
    "Routine": 0.25,
}


def _split_set(value: str | float | None) -> set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    return {item.strip() for item in str(value).split(";") if item.strip()}


def eligible_radiologists(study: pd.Series, radiologists: pd.DataFrame) -> pd.DataFrame:
    """Return active radiologists eligible for a study based on client and modality."""
    client = str(study["client"])
    modality = str(study["modality"])

    def eligible(row: pd.Series) -> bool:
        return (
            bool(row["active"])
            and client in _split_set(row["credentialed_clients"])
            and modality in _split_set(row["modalities"])
        )

    mask = radiologists.apply(eligible, axis=1)
    return radiologists.loc[mask].copy()


def score_study(study: pd.Series, radiologists: pd.DataFrame) -> dict:
    """
    Calculate an explainable operational risk score.

    This MVP deliberately keeps contractual and credentialing rules deterministic.
    It does not make clinical decisions or interpret images.
    """
    eligible = eligible_radiologists(study, radiologists)

    sla = max(float(study["sla_minutes"]), 1.0)
    age = max(float(study["age_minutes"]), 0.0)
    sla_pressure = min(age / sla, 1.25)

    if eligible.empty:
        eligible_count = 0
        capacity_pressure = 1.0
        eligibility_pressure = 1.0
        avg_available_slots = 0.0
    else:
        eligible_count = len(eligible)
        utilization = (
            eligible["current_workload"].astype(float)
            / eligible["max_workload"].astype(float).clip(lower=1)
        ).clip(lower=0, upper=1.5)
        capacity_pressure = float(utilization.mean().clip(0, 1))
        eligibility_pressure = 1 / min(eligible_count, 5)
        avg_available_slots = float(
            (eligible["max_workload"] - eligible["current_workload"]).clip(lower=0).mean()
        )

    priority_pressure = PRIORITY_WEIGHT.get(str(study["priority"]), 0.4)

    risk_score = round(
        min(
            100,
            (
                55 * min(sla_pressure, 1)
                + 20 * capacity_pressure
                + 15 * eligibility_pressure
                + 10 * priority_pressure
                + (10 if sla_pressure >= 1 else 0)
            ),
        ),
        1,
    )

    if eligible_count == 0 or risk_score >= 75:
        band = "RED"
    elif risk_score >= 50:
        band = "YELLOW"
    else:
        band = "GREEN"

    minutes_to_sla = round(sla - age, 1)

    if eligible_count == 0:
        action = "Escalate now: no active eligible radiologist found for this client/modality."
    elif minutes_to_sla <= 0:
        action = "Escalate SLA breach and assign the least-loaded eligible radiologist."
    elif band == "RED":
        action = "Prioritize and route to the least-loaded eligible radiologist; ambassador review now."
    elif band == "YELLOW":
        action = "Watch closely and rebalance if queue pressure increases."
    else:
        action = "No intervention needed; continue automated monitoring."

    return {
        "risk_score": risk_score,
        "risk_band": band,
        "eligible_radiologists": eligible_count,
        "minutes_to_sla": minutes_to_sla,
        "avg_available_slots": round(avg_available_slots, 1),
        "recommended_action": action,
    }


def score_queue(studies: pd.DataFrame, radiologists: pd.DataFrame) -> pd.DataFrame:
    scored = studies.copy()
    details = scored.apply(lambda row: pd.Series(score_study(row, radiologists)), axis=1)
    scored = pd.concat([scored.reset_index(drop=True), details.reset_index(drop=True)], axis=1)
    return scored.sort_values(
        ["risk_score", "age_minutes"], ascending=[False, False]
    ).reset_index(drop=True)


def summarize_queue(scored: pd.DataFrame) -> dict:
    return {
        "total_studies": int(len(scored)),
        "red": int((scored["risk_band"] == "RED").sum()),
        "yellow": int((scored["risk_band"] == "YELLOW").sum()),
        "green": int((scored["risk_band"] == "GREEN").sum()),
        "sla_breached": int((scored["minutes_to_sla"] <= 0).sum()),
        "no_eligible_reader": int((scored["eligible_radiologists"] == 0).sum()),
    }
