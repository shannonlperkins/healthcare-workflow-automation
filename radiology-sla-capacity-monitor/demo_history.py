"""Reproducible synthetic counts, with explicit zero-volume hours.

These patterns are invented for a portfolio demo, not measured at any employer.
"""
import numpy as np
import pandas as pd

from forecast_engine import DEMO_NOW

# Mean arrivals per hour before invented time-of-day/day-of-week effects.
STREAMS = [
    ("Metro General", "CT", "STAT", 5.5),
    ("Metro General", "CT", "Routine", 2.0),
    ("Metro General", "XR", "Urgent", 3.0),
    ("Prairie Medical", "CT", "STAT", 4.0),
    ("Prairie Medical", "MRI", "STAT", 1.8),
    ("Prairie Medical", "XR", "Urgent", .4),
    ("River Valley", "CT", "Urgent", 3.5),
    ("River Valley", "MRI", "STAT", 2.0),
    ("River Valley", "MRI", "Routine", 1.2),
    ("Summit Health", "XR", "Routine", 4.0),
    ("Summit Health", "US", "STAT", 2.0),
    ("Summit Health", "MRI", "Urgent", 1.5),
]


def generate_history(days=56, seed=2026):
    rng = np.random.default_rng(seed)
    rows = []
    for hour in pd.date_range(DEMO_NOW - pd.Timedelta(days=days),
                              DEMO_NOW - pd.Timedelta(hours=1), freq="h"):
        # Evening ED surge and quieter early mornings in America/Chicago.
        local = hour.tz_convert("America/Chicago")
        factor = 1.45 if 17 <= local.hour <= 21 else .55 if 1 <= local.hour <= 6 else 1.
        factor *= 1.12 if local.dayofweek in (0, 1) else .9 if local.dayofweek >= 5 else 1.
        for client, modality, priority, base in STREAMS:
            rows.append({"hour_start": hour, "client": client, "modality": modality,
                         "priority": priority, "arrivals": int(rng.poisson(base * factor))})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from pathlib import Path
    path = Path(__file__).resolve().parent / "data" / "historical_arrivals.csv"
    generate_history().to_csv(path, index=False)
    print(f"Wrote synthetic history to {path}")
