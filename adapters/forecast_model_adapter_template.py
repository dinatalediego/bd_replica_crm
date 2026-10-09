"""
Forecast Factory Contract v1 — model adapter template.

Every future forecasting model should end by producing:
1) one run manifest,
2) one or more canonical prediction rows.

Model-specific code may use sklearn, statsmodels, xgboost, prophet, neural nets,
hierarchical methods, ensembles, etc. Power BI never needs to know which one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

import pandas as pd


REQUIRED_PREDICTION_COLUMNS = [
    "project_key",
    "target_name",
    "target_unit",
    "segment_key",
    "forecast_for_period",
    "horizon_months",
    "prediction",
    "prediction_lower",
    "prediction_upper",
    "interval_level",
    "naive_method",
    "naive_prediction",
    "evidence_class",
]


@dataclass(frozen=True)
class RunManifest:
    model_version_id: int
    issued_at: datetime
    data_cutoff_date: date
    training_start_date: date
    training_end_date: date
    feature_version: str
    dataset_snapshot_id: str
    code_sha: str


def validate_prediction_frame(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_PREDICTION_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing Forecast Factory columns: {missing}")

    if df.empty:
        raise ValueError("Forecast output cannot be empty.")

    if (df["horizon_months"] < 1).any():
        raise ValueError("horizon_months must be >= 1.")

    if (df["prediction_lower"] > df["prediction"]).any():
        raise ValueError("prediction_lower cannot exceed prediction.")

    if (df["prediction"] > df["prediction_upper"]).any():
        raise ValueError("prediction cannot exceed prediction_upper.")

    if df["naive_prediction"].isna().any():
        raise ValueError("naive_prediction is mandatory.")

    invalid_class = ~df["evidence_class"].isin(["PROSPECTIVE", "BACKTEST"])
    if invalid_class.any():
        raise ValueError("evidence_class must be PROSPECTIVE or BACKTEST.")


def build_predictions_from_model_output(
    *,
    model_output: pd.DataFrame,
    target_name: str,
    target_unit: str,
    naive_method: str,
    evidence_class: str,
) -> pd.DataFrame:
    """
    Expected model_output columns:
      project_key, segment_key, forecast_for_period, horizon_months,
      prediction, prediction_lower, prediction_upper, naive_prediction
    """
    out = model_output.copy()
    out["target_name"] = target_name
    out["target_unit"] = target_unit
    out["naive_method"] = naive_method
    out["evidence_class"] = evidence_class
    out["interval_level"] = out.get("interval_level", 0.80)

    cols = REQUIRED_PREDICTION_COLUMNS
    validate_prediction_frame(out[cols])
    return out[cols]
