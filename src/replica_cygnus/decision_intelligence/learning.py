from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss


@dataclass(frozen=True)
class LearningReport:
    observations: int
    action_rate: float
    outcome_rate: float
    realized_incremental_value: float
    brier_score: float | None


def evaluate_decisions(
    data: pd.DataFrame,
    probability_col: str = "predicted_probability",
    action_col: str = "action_taken",
    outcome_col: str = "outcome",
    realized_value_col: str = "realized_incremental_value",
) -> LearningReport:
    required = {action_col, outcome_col, realized_value_col}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Faltan columnas de feedback: {', '.join(sorted(missing))}")
    frame = data.dropna(subset=[action_col, outcome_col, realized_value_col]).copy()
    brier = None
    if probability_col in frame.columns and frame[probability_col].notna().all() and len(frame):
        brier = float(brier_score_loss(frame[outcome_col].astype(int), frame[probability_col]))
    return LearningReport(
        observations=len(frame),
        action_rate=float(np.mean(frame[action_col].astype(bool))) if len(frame) else 0.0,
        outcome_rate=float(np.mean(frame[outcome_col].astype(float))) if len(frame) else 0.0,
        realized_incremental_value=float(frame[realized_value_col].sum()) if len(frame) else 0.0,
        brier_score=brier,
    )
