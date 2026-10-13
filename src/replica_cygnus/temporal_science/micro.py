from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


NUMERIC_FEATURES = [
    "dormitorios", "area_total", "area_relativa", "precio_relativo",
    "mes_vida", "mes_calendario", "leads_4w", "proformas_4w",
    "interacciones_4w", "visitas_4w",
]
CATEGORICAL_FEATURES = ["codigo_proyecto", "tipologia", "moneda", "estado_construccion"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class MicroFit:
    horizon_days: int
    model_run_id: str
    model_family: str
    evidence_level: str
    role: str
    metrics: dict
    feature_contract: dict
    train_start: object
    train_end: object
    validation_start: object
    validation_end: object
    rows_train: int
    rows_validation: int
    artifact_path: str | None
    predictions: pd.DataFrame


def _pipeline() -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value=0.0)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="MISSING")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    prep = ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ])
    return Pipeline([
        ("prep", prep),
        ("model", LogisticRegression(max_iter=1200, class_weight="balanced", random_state=42)),
    ])


def _metrics(y: pd.Series, probability: np.ndarray) -> dict:
    yv = pd.to_numeric(y, errors="raise").astype(int).to_numpy()
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    out = {
        "rows": int(len(yv)),
        "positive_rate": float(yv.mean()) if len(yv) else None,
        "brier": float(brier_score_loss(yv, p)) if len(yv) else None,
        "log_loss": float(log_loss(yv, p, labels=[0, 1])) if len(yv) else None,
        "roc_auc": None,
    }
    if len(np.unique(yv)) == 2:
        out["roc_auc"] = float(roc_auc_score(yv, p))
    return out


def _requires_review(value) -> bool:
    if isinstance(value, dict):
        return bool(value.get("requiere_revision", False))
    text = str(value).lower()
    return "requiere_revision" in text and ("true" in text or "'requiere_revision': 1" in text)


def _select_evidence(frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, str]:
    h = frame[frame.horizonte_dias.eq(horizon) & frame.maduro & frame.venta_vigente.notna()].copy()
    observed = h[h.evidencia.eq("OBSERVADO") & h.elegible_validacion_prospectiva.fillna(False)]
    if len(observed) >= 200 and observed.fecha_corte.nunique() >= 4 and observed.venta_vigente.nunique() == 2:
        return observed, "PROSPECTIVE_OBSERVED"
    reconstructed = h[h.evidencia.eq("RECONSTRUIDO")].copy()
    if "calidad" in reconstructed:
        reconstructed = reconstructed[~reconstructed.calidad.map(_requires_review)]
    return reconstructed, "HISTORICAL_DIAGNOSTIC_SHADOW"


def _temporal_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(pd.to_datetime(frame.fecha_corte).dropna().unique())
    if len(dates) < 3:
        return frame.iloc[0:0], frame.iloc[0:0]
    cut_idx = max(1, int(np.floor(len(dates) * 0.8)))
    cut_idx = min(cut_idx, len(dates) - 1)
    validation_start = pd.Timestamp(dates[cut_idx])
    d = frame.copy()
    d["fecha_corte"] = pd.to_datetime(d.fecha_corte)
    d["ventana_fin"] = pd.to_datetime(d.ventana_fin)
    # Embargo: every training outcome must have matured before validation begins.
    train = d[d.ventana_fin.lt(validation_start)].copy()
    validation = d[d.fecha_corte.ge(validation_start)].copy()
    return train, validation


def fit_micro_horizon(frame: pd.DataFrame, horizon: int, output_dir: Path) -> MicroFit | None:
    history, evidence_level = _select_evidence(frame, horizon)
    if len(history) < 80 or history.venta_vigente.nunique() < 2:
        return None
    train, validation = _temporal_split(history)
    if len(train) < 60 or len(validation) < 20 or train.venta_vigente.nunique() < 2:
        return None

    base_probability = float(train.venta_vigente.mean())
    baseline_pred = np.full(len(validation), base_probability, dtype=float)
    baseline_metrics = _metrics(validation.venta_vigente, baseline_pred)

    candidate = _pipeline()
    candidate.fit(train[ALL_FEATURES], train.venta_vigente.astype(int))
    candidate_pred = candidate.predict_proba(validation[ALL_FEATURES])[:, 1]
    candidate_metrics = _metrics(validation.venta_vigente, candidate_pred)

    improvement = None
    if baseline_metrics["brier"] not in (None, 0):
        improvement = 1.0 - candidate_metrics["brier"] / baseline_metrics["brier"]
    selected = bool(
        len(validation) >= 50
        and candidate_metrics["brier"] is not None
        and baseline_metrics["brier"] is not None
        and candidate_metrics["brier"] <= baseline_metrics["brier"] * 0.98
    )
    family = "micro_logit" if selected else "micro_base_rate"
    role = "CHAMPION" if selected and evidence_level == "PROSPECTIVE_OBSERVED" else "SHADOW"

    current = frame[
        frame.horizonte_dias.eq(horizon)
        & frame.evidencia.eq("OBSERVADO")
        & frame.disponible.fillna(False)
    ].copy()
    if len(current):
        latest_cut = pd.to_datetime(current.fecha_corte).max()
        current = current[pd.to_datetime(current.fecha_corte).eq(latest_cut)].copy()
    if len(current):
        probabilities = candidate.predict_proba(current[ALL_FEATURES])[:, 1] if selected else np.full(len(current), base_probability)
        predictions = current[["codigo_unidad", "codigo_proyecto", "fecha_corte", "information_cutoff"]].copy()
        predictions["probability"] = probabilities
    else:
        predictions = pd.DataFrame(columns=["codigo_unidad", "codigo_proyecto", "fecha_corte", "information_cutoff", "probability"])

    model_run_id = str(uuid4())
    artifact_path = None
    if selected:
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = output_dir / f"micro_{horizon}d_{model_run_id}.joblib"
        joblib.dump(candidate, artifact)
        artifact_path = str(artifact)

    metrics = {
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "brier_improvement": improvement,
        "selection_rule": "candidate Brier <= 98% of baseline Brier on embargoed temporal validation with >=50 rows",
        "selected_family": family,
    }
    contract = {
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "target": "venta_vigente",
        "horizon_days": horizon,
        "split": "ordered cut dates; training outcomes must mature before validation start",
        "point_in_time_policy": "OBSERVADO preferred; reconstructed history is shadow-only",
    }
    return MicroFit(
        horizon_days=horizon,
        model_run_id=model_run_id,
        model_family=family,
        evidence_level=evidence_level,
        role=role,
        metrics=metrics,
        feature_contract=contract,
        train_start=pd.to_datetime(train.fecha_corte).min().date(),
        train_end=pd.to_datetime(train.fecha_corte).max().date(),
        validation_start=pd.to_datetime(validation.fecha_corte).min().date(),
        validation_end=pd.to_datetime(validation.fecha_corte).max().date(),
        rows_train=len(train),
        rows_validation=len(validation),
        artifact_path=artifact_path,
        predictions=predictions,
    )
