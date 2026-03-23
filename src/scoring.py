from __future__ import annotations

DEFAULT_SCORING_WEIGHTS = {
    "pressure": {"existing": 1.0, "proposed": 1.5, "denied": 0.5, "inventory": 0.75},
    "economic": {"poverty": 0.30, "minority": 0.25, "income": 0.20, "housing": 0.10, "energy": 0.15},
    "cumulative": {"aqi": 0.30, "ozone": 0.20, "pm25": 0.20, "energy": 0.20, "electricity": 0.10},
}

