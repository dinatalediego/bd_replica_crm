from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from psycopg.rows import dict_row
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


DATA_SQL = """
select
    separation_id,
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    asesor,
    tipo_unidad_principal,
    fecha_separacion,
    snapshot_at,
    landmark_day,
    days_since_separation,
    proforma_age_days_at_snapshot,
    proforma_age_days_at_separation,
    snapshot_iso_weekday,
    snapshot_month,
    label_measurement_regime,
    target_fall_within_30d,
    lifecycle_balancing_weight,
    prediction_horizon_days,
    feature_scope,
    interaction_features_certified,
    evaluation_contract
from features.separation_fall_training_30d
order by snapshot_at, separation_id, landmark_day
"""

HEALTH_SQL = "select * from features.v_separation_fall_training_30d_health"

TARGET = "target_fall_within_30d"
WEIGHT = "lifecycle_balancing_weight"
GROUP = "separation_id"
DATE = "snapshot_at"
POST_2026 = "POST_2026_PAYMENT_DATE_REGIME"

NUMERIC_FEATURES = [
    "days_since_separation",
    "proforma_age_days_at_snapshot",
    "proforma_age_days_at_separation",
    "snapshot_iso_weekday",
    "snapshot_month",
]
CATEGORICAL_FEATURES = ["codigo_proyecto", "tipo_unidad_principal"]
PROHIBITED_FEATURES = {
    "motivo_caida_segun_asesor",
    "cambio_de_departamento",
    "depa_del_cambio",
    "outcome_at",
    "horizon_end_at",
    "training_outcome_class",
}


@dataclass(frozen=True)
class SplitSpec:
    name: str
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    train_regime: str | None = None
    test_regime: str | None = None
    train_end: pd.Timestamp | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark gobernado para riesgo de caída dentro de 30 días. "
            "Usa split out-of-time y elimina del train cualquier separation_id "
            "que aparezca en test para evitar leakage entre snapshots."
        )
    )
    parser.add_argument("--historical-start", default="2022-01-01")
    parser.add_argument("--cross-regime-test-start", default="2026-01-01")
    parser.add_argument("--current-regime-test-start", default="2026-05-01")
    parser.add_argument("--include-advisor", action="store_true")
    parser.add_argument(
        "--output-dir",
        default="reports/separation_fall_30d_benchmark",
    )
    return parser.parse_args()


def fetch_rows(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def _safe_auc(y: np.ndarray, score: np.ndarray, weight: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, score, sample_weight=weight))


def _expected_calibration_error(
    y: np.ndarray,
    score: np.ndarray,
    weight: np.ndarray,
    bins: int = 10,
) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.clip(np.digitize(score, edges[1:-1], right=True), 0, bins - 1)
    total_weight = float(weight.sum())
    if total_weight <= 0:
        return float("nan")
    ece = 0.0
    for idx in range(bins):
        mask = bucket == idx
        if not mask.any():
            continue
        w = weight[mask]
        mass = float(w.sum())
        observed = float(np.average(y[mask], weights=w))
        predicted = float(np.average(score[mask], weights=w))
        ece += mass / total_weight * abs(observed - predicted)
    return float(ece)


def _top_k_metrics(y: np.ndarray, score: np.ndarray, k: int) -> dict[str, float | None]:
    if len(y) == 0:
        return {f"precision_at_{k}": None, f"recall_at_{k}": None, f"lift_at_{k}": None}
    n = min(k, len(y))
    order = np.argsort(-score, kind="stable")[:n]
    positives = int(y.sum())
    precision = float(y[order].mean())
    recall = float(y[order].sum() / positives) if positives else None
    prevalence = float(y.mean())
    lift = float(precision / prevalence) if prevalence > 0 else None
    return {
        f"precision_at_{k}": precision,
        f"recall_at_{k}": recall,
        f"lift_at_{k}": lift,
    }


def metric_row(
    *,
    split_name: str,
    model_name: str,
    test_df: pd.DataFrame,
    score: np.ndarray,
) -> dict[str, Any]:
    y = test_df[TARGET].astype(int).to_numpy()
    weight = test_df[WEIGHT].astype(float).to_numpy()
    prevalence = float(np.average(y, weights=weight))
    row: dict[str, Any] = {
        "split": split_name,
        "model": model_name,
        "test_rows": int(len(test_df)),
        "test_lifecycles": int(test_df[GROUP].nunique()),
        "weighted_prevalence": prevalence,
        "pr_auc": float(average_precision_score(y, score, sample_weight=weight)),
        "roc_auc": _safe_auc(y, score, weight),
        "brier": float(brier_score_loss(y, score, sample_weight=weight)),
        "ece_10": _expected_calibration_error(y, score, weight, bins=10),
    }
    row.update(_top_k_metrics(y, score, 10))
    row.update(_top_k_metrics(y, score, 20))
    return row


def split_group_safe(df: pd.DataFrame, spec: SplitSpec) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    train_mask = df[DATE].ge(spec.train_start) & df[DATE].lt(spec.test_start)
    if spec.train_end is not None:
        train_mask &= df[DATE].lt(spec.train_end)
    test_mask = df[DATE].ge(spec.test_start)

    if spec.train_regime:
        train_mask &= df["label_measurement_regime"].eq(spec.train_regime)
    if spec.test_regime:
        test_mask &= df["label_measurement_regime"].eq(spec.test_regime)

    test = df.loc[test_mask].copy()
    test_groups = set(test[GROUP].astype(str))
    train = df.loc[train_mask & ~df[GROUP].astype(str).isin(test_groups)].copy()

    overlap = set(train[GROUP].astype(str)).intersection(test_groups)
    if overlap:
        raise RuntimeError(f"Group leakage detectado en split {spec.name}: {len(overlap)} separation_id")

    health = {
        "split": spec.name,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_lifecycles": int(train[GROUP].nunique()),
        "test_lifecycles": int(test[GROUP].nunique()),
        "group_overlap": 0,
        "train_min_snapshot": str(train[DATE].min()) if not train.empty else None,
        "train_max_snapshot": str(train[DATE].max()) if not train.empty else None,
        "test_min_snapshot": str(test[DATE].min()) if not test.empty else None,
        "test_max_snapshot": str(test[DATE].max()) if not test.empty else None,
        "train_positive_rows": int(train[TARGET].sum()) if not train.empty else 0,
        "test_positive_rows": int(test[TARGET].sum()) if not test.empty else 0,
    }
    return train, test, health


def landmark_baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    overall = float(np.average(train[TARGET], weights=train[WEIGHT]))
    grouped = (
        train.groupby("landmark_day", dropna=False)
        .apply(lambda g: np.average(g[TARGET], weights=g[WEIGHT]), include_groups=False)
        .to_dict()
    )
    return test["landmark_day"].map(grouped).fillna(overall).astype(float).to_numpy()


def make_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", min_frequency=2, sparse_output=False),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipe, numeric),
            ("categorical", categorical_pipe, categorical),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


def model_factories(numeric: list[str], categorical: list[str]) -> dict[str, Callable[[], Pipeline]]:
    def pipe(model: Any) -> Pipeline:
        return Pipeline([("preprocess", make_preprocessor(numeric, categorical)), ("model", model)])

    return {
        "logistic_regression": lambda: pipe(
            LogisticRegression(max_iter=2000, class_weight=None, random_state=42)
        ),
        "random_forest": lambda: pipe(
            RandomForestClassifier(
                n_estimators=400,
                min_samples_leaf=8,
                max_features="sqrt",
                random_state=42,
                n_jobs=-1,
            )
        ),
        "hist_gradient_boosting": lambda: pipe(
            HistGradientBoostingClassifier(
                learning_rate=0.05,
                max_iter=250,
                max_leaf_nodes=15,
                min_samples_leaf=20,
                l2_regularization=1.0,
                random_state=42,
            )
        ),
    }


def main() -> int:
    args = parse_args()
    settings = load_settings()
    output_dir = settings.project_root / Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        rows = fetch_rows(conn, DATA_SQL)
        health_rows = fetch_rows(conn, HEALTH_SQL)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("features.separation_fall_training_30d no tiene filas.")

    df[DATE] = pd.to_datetime(df[DATE])
    df[TARGET] = df[TARGET].astype(int)
    df[WEIGHT] = df[WEIGHT].astype(float)

    if df["interaction_features_certified"].fillna(False).any():
        raise RuntimeError("El benchmark v1 espera interaction_features_certified=false.")
    if not df["feature_scope"].eq("STRUCTURAL_TEMPORAL_30D_V1").all():
        raise RuntimeError("Feature scope inesperado; revisar contrato antes de modelar.")

    numeric = list(NUMERIC_FEATURES)
    categorical = list(CATEGORICAL_FEATURES)
    if args.include_advisor:
        categorical.append("asesor")

    if PROHIBITED_FEATURES.intersection(numeric + categorical):
        raise RuntimeError("Se intentó incluir una feature post-outcome/prohibida.")

    specs = [
        SplitSpec(
            name="cross_regime_pre2026_to_post2026",
            train_start=pd.Timestamp(args.historical_start),
            test_start=pd.Timestamp(args.cross_regime_test_start),
            test_regime=POST_2026,
        ),
        SplitSpec(
            name="current_regime_2026_early_to_recent",
            train_start=pd.Timestamp(args.cross_regime_test_start),
            test_start=pd.Timestamp(args.current_regime_test_start),
            train_regime=POST_2026,
            test_regime=POST_2026,
        ),
    ]

    metrics: list[dict[str, Any]] = []
    predictions: list[pd.DataFrame] = []
    split_health: list[dict[str, Any]] = []

    for spec in specs:
        train, test, split_meta = split_group_safe(df, spec)
        split_health.append(split_meta)
        if train.empty or test.empty or train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
            split_meta["status"] = "SKIPPED_INSUFFICIENT_CLASS_COVERAGE"
            continue
        split_meta["status"] = "OK"

        y_train = train[TARGET].astype(int)
        w_train = train[WEIGHT].astype(float)
        train_prevalence = float(np.average(y_train, weights=w_train))

        baseline_scores = {
            "prevalence_baseline": np.full(len(test), train_prevalence, dtype=float),
            "landmark_prevalence_baseline": landmark_baseline(train, test),
        }

        for name, score in baseline_scores.items():
            metrics.append(metric_row(split_name=spec.name, model_name=name, test_df=test, score=score))
            out = test[[GROUP, "codigo_proforma", "codigo_unidad", "codigo_proyecto", DATE, "landmark_day", TARGET]].copy()
            out["split"] = spec.name
            out["model"] = name
            out["score"] = score
            predictions.append(out)

        feature_cols = numeric + categorical
        for model_name, factory in model_factories(numeric, categorical).items():
            model = factory()
            model.fit(train[feature_cols], y_train, model__sample_weight=w_train)
            score = model.predict_proba(test[feature_cols])[:, 1]
            metrics.append(metric_row(split_name=spec.name, model_name=model_name, test_df=test, score=score))
            out = test[[GROUP, "codigo_proforma", "codigo_unidad", "codigo_proyecto", DATE, "landmark_day", TARGET]].copy()
            out["split"] = spec.name
            out["model"] = model_name
            out["score"] = score
            predictions.append(out)

    metrics_df = pd.DataFrame(metrics)
    split_df = pd.DataFrame(split_health)
    pred_df = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()

    if not metrics_df.empty:
        metrics_df = metrics_df.sort_values(["split", "pr_auc", "brier"], ascending=[True, False, True])
        metrics_df.to_csv(output_dir / "metrics.csv", index=False, encoding="utf-8-sig")
    split_df.to_csv(output_dir / "split_health.csv", index=False, encoding="utf-8-sig")
    if not pred_df.empty:
        pred_df.to_csv(output_dir / "predictions.csv", index=False, encoding="utf-8-sig")

    summary = {
        "status": "OK" if not metrics_df.empty else "NO_VALID_BENCHMARK_SPLIT",
        "source_health": health_rows[0] if health_rows else {},
        "feature_scope": "STRUCTURAL_TEMPORAL_30D_V1",
        "numeric_features": numeric,
        "categorical_features": categorical,
        "advisor_included": bool(args.include_advisor),
        "interaction_features_certified": False,
        "group_leakage_policy": "test separation_id is removed from train",
        "models": [
            "prevalence_baseline",
            "landmark_prevalence_baseline",
            "logistic_regression",
            "random_forest",
            "hist_gradient_boosting",
        ],
        "splits": split_health,
        "outputs": ["metrics.csv", "split_health.csv", "predictions.csv"],
        "interpretation": (
            "Research benchmark only. Promotion requires out-of-time lift over baselines, "
            "calibration review, subgroup stability and shadow-mode evidence."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if not metrics_df.empty:
        print("\n=== METRICS ===")
        print(metrics_df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
