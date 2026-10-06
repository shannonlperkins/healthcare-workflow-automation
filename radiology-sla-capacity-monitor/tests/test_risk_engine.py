import pandas as pd

from risk_engine import score_queue, score_study


def test_no_eligible_reader_is_red():
    study = pd.Series(
        {
            "client": "Client X",
            "modality": "CT",
            "priority": "STAT",
            "sla_minutes": 30,
            "age_minutes": 5,
        }
    )
    radiologists = pd.DataFrame(
        [
            {
                "radiologist": "Dr. A",
                "active": True,
                "modalities": "MRI",
                "credentialed_clients": "Client X",
                "current_workload": 1,
                "max_workload": 10,
            }
        ]
    )
    result = score_study(study, radiologists)
    assert result["risk_band"] == "RED"
    assert result["eligible_radiologists"] == 0


def test_queue_sorts_highest_risk_first():
    studies = pd.DataFrame(
        [
            {
                "study_id": "A",
                "client": "X",
                "modality": "CT",
                "priority": "Routine",
                "sla_minutes": 480,
                "age_minutes": 20,
            },
            {
                "study_id": "B",
                "client": "X",
                "modality": "CT",
                "priority": "STAT",
                "sla_minutes": 30,
                "age_minutes": 28,
            },
        ]
    )
    radiologists = pd.DataFrame(
        [
            {
                "radiologist": "Dr. A",
                "active": True,
                "modalities": "CT",
                "credentialed_clients": "X",
                "current_workload": 5,
                "max_workload": 10,
            }
        ]
    )
    scored = score_queue(studies, radiologists)
    assert scored.iloc[0]["study_id"] == "B"
