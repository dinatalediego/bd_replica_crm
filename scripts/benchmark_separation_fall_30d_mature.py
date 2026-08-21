from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

import benchmark_separation_fall_30d as base
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


# Fixed-horizon binary classification requires the complete 30-day observation
# window for BOTH positive and negative rows. The v1 audit intentionally keeps
# known events observed before the data cutoff even when horizon_end_at extends
# beyond the cutoff; that is useful for survival/censoring research, but it can
# bias a conventional binary benchmark near the right edge of the dataset.
# This benchmark therefore matures every label before model fitting/evaluation.
DATA_SQL = """
with mature as (
    select
        a.separation_id,
        a.codigo_proforma,
        a.codigo_unidad,
        a.codigo_proyecto,
        a.asesor,
        a.tipo_unidad_principal,
        a.fecha_separacion,
        a.snapshot_at,
        a.horizon_end_at,
        a.observed_through,
        a.landmark_day,
        a.days_since_separation,
        a.proforma_age_days_at_snapshot,
        a.proforma_age_days_at_separation,
        a.snapshot_iso_weekday,
        a.snapshot_month,
        a.label_measurement_regime,
        a.target_fall_within_30d,
        a.prediction_horizon_days,
        a.feature_scope,
        a.interaction_features_certified,
        a.evaluation_contract
    from features.v_separation_fall_training_30d_audit a
    where a.target_fall_within_30d is not null
      and a.horizon_end_at <= a.observed_through
), weighted as (
    select
        m.*,
        count(*) over (partition by m.separation_id) as mature_snapshots_per_separation
    from mature m
)
select
    w.*,
    (1.0 / nullif(w.mature_snapshots_per_separation, 0))::numeric
        as lifecycle_balancing_weight
from weighted w
order by snapshot_at, separation_id, landmark_day
"""

HEALTH_SQL = """
select
    count(*) filter (
        where target_fall_within_30d is not null
    )::bigint as v1_labeled_snapshot_rows,
    count(*) filter (
        where target_fall_within_30d is not null
          and horizon_end_at <= observed_through
    )::bigint as mature_labeled_snapshot_rows,
    count(distinct separation_id) filter (
        where target_fall_within_30d is not null
          and horizon_end_at <= observed_through
    )::bigint as mature_labeled_lifecycles,
    count(*) filter (
        where target_fall_within_30d = 1
          and horizon_end_at <= observed_through
    )::bigint as mature_fall_rows,
    count(*) filter (
        where target_fall_within_30d = 0
          and horizon_end_at <= observed_through
    )::bigint as mature_no_fall_rows,
    count(*) filter (
        where target_fall_within_30d is not null
          and horizon_end_at > observed_through
    )::bigint as labeled_rows_removed_for_incomplete_horizon,
    count(*) filter (
        where target_fall_within_30d = 1
          and horizon_end_at > observed_through
    )::bigint as positive_rows_removed_for_incomplete_horizon,
    max(observed_through) as observed_through,
    max(horizon_end_at) filter (
        where target_fall_within_30d is not null
          and horizon_end_at <= observed_through
    ) as latest_mature_horizon_end_at
from features.v_separation_fall_training_30d_audit
"""

TARGET = base.TARGET
WEIGHT = base.WEIGHT
GROUP = base.GROUP
DATE = base.DATE


def safe_auc(y: np.ndarray, score: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, score))


def top_k(y: np.ndarray, score: np.ndarray, k: int) -> dict[str, float | None]:
    if len(y) == 0:
        return {
            f"precision_at_{k}": None,
            f"recall_at_{k}": None,
            f"lift_at_{k}": None,
        }
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


def first_touch_metrics(
    *,
    split_name: str,
    model_name: str,
    test: pd.DataFrame,
    score: np.ndarray,
) -> dict[str, Any]:
    scored = test[[GROUP, DATE, "landmark_day", TARGET]].copy()
    scored["score"] = score
    first = (
        scored.sort_values([GROUP, DATE, "landmark_day"], kind="stable")
        .groupby(GROUP, as_index=False, sort=False)
        .head(1)
        .copy()
    )
    y = first[TARGET].astype(int).to_numpy()
    s = first["score"].astype(float).to_numpy()
    prevalence = float(y.mean()) if len(y) else float("nan")
    row: dict[str, Any] = {
        "split": split_name,
        "model": model_name,
        "evaluation_unit": "FIRST_ELIGIBLE_TEST_SNAPSHOT_PER_SEPARATION",
        "rows": int(len(first)),
        "distinct_lifecycles": int(first[GROUP].nunique()),
        "prevalence": prevalence,
        "pr_auc": float(average_precision_score(y, s)) if len(np.unique(y)) >= 2 else None,
        "roc_auc": safe_auc(y, s),
        "brier": float(brier_score_loss(y, s)) if len(y) else None,
    }
    row.update(top_k(y, s, 10))
    row.update(top_k(y, s, 20))
    return row


def landmark_metrics(
    *,
    split_name: str,
    model_name: str,
    test: pd.DataFrame,
    score: np.ndarray,
) -> list[dict[str, Any]]:
    scored = test[[GROUP, "landmark_day", TARGET]].copy()
    scored["score"] = score
    rows: list[dict[str, Any]] = []
    for landmark_day, g in scored.groupby("landmark_day", sort=True):
        y = g[TARGET].astype(int).to_numpy()
        s = g["score"].astype(float).to_numpy()
        rows.append(
            {
                "split": split_name,
                "model": model_name,
                "landmark_day": int(landmark_day),
                "rows": int(len(g)),
                "distinct_lifecycles": int(g[GROUP].nunique()),
                "positives": int(y.sum()),
                "prevalence": float(y.mean()) if len(y) else None,
                "pr_auc": float(average_precision_score(y, s)) if len(np.unique(y)) >= 2 else None,
                "roc_auc": safe_auc(y, s),
                "brier": float(brier_score_loss(y, s)) if len(y) else None,
            }
        )
    return rows


def main() -> int:
    args = base.parse_args()
    settings = load_settings()
    output_dir = settings.project_root / Path(args.output_dir + "_mature")
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        rows = base.fetch_rows(conn, DATA_SQL)
        health_rows = base.fetch_rows(conn, HEALTH_SQL)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No hay labels de 30 días con horizonte completamente maduro.")

    df[DATE] = pd.to_datetime(df[DATE])
    df[TARGET] = df[TARGET].astype(int)
    df[WEIGHT] = df[WEIGHT].astype(float)

    if (pd.to_datetime(df["horizon_end_at"]) > pd.to_datetime(df["observed_through"])).any():
        raise RuntimeError("Gate falló: existe una fila etiquetada sin 30 días completos de seguimiento.")
    if df["interaction_features_certified"].fillna(False).any():
        raise RuntimeError("El benchmark maduro v2 espera interaction_features_certified=false.")

    numeric = list(base.NUMERIC_FEATURES)
    categorical = list(base.CATEGORICAL_FEATURES)
    if args.include_advisor:
        categorical.append("asesor")
    if base.PROHIBITED_FEATURES.intersection(numeric + categorical):
        raise RuntimeError("Se intentó incluir una feature post-outcome/prohibida.")

    specs = [
        base.SplitSpec(
            name="cross_regime_pre2026_to_post2026",
            train_start=pd.Timestamp(args.historical_start),
            test_start=pd.Timestamp(args.cross_regime_test_start),
            test_regime=base.POST_2026,
        ),
        base.SplitSpec(
            name="current_regime_2026_early_to_recent",
            train_start=pd.Timestamp(args.cross_regime_test_start),
            test_start=pd.Timestamp(args.current_regime_test_start),
            train_regime=base.POST_2026,
            test_regime=base.POST_2026,
        ),
    ]

    snapshot_metrics: list[dict[str, Any]] = []
    first_touch: list[dict[str, Any]] = []
    by_landmark: list[dict[str, Any]] = []
    predictions: list[pd.DataFrame] = []
    split_health: list[dict[str, Any]] = []

    for spec in specs:
        train, test, split_meta = base.split_group_safe(df, spec)
        split_health.append(split_meta)
        if train.empty or test.empty or train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
            split_meta["status"] = "SKIPPED_INSUFFICIENT_CLASS_COVERAGE"
            continue
        split_meta["status"] = "OK"

        y_train = train[TARGET].astype(int)
        w_train = train[WEIGHT].astype(float)
        train_prevalence = float(np.average(y_train, weights=w_train))
        score_sets: dict[str, np.ndarray] = {
            "prevalence_baseline": np.full(len(test), train_prevalence, dtype=float),
            "landmark_prevalence_baseline": base.landmark_baseline(train, test),
        }

        feature_cols = numeric + categorical
        for model_name, factory in base.model_factories(numeric, categorical).items():
            model = factory()
            model.fit(train[feature_cols], y_train, model__sample_weight=w_train)
            score_sets[model_name] = model.predict_proba(test[feature_cols])[:, 1]

        for model_name, score in score_sets.items():
            # Weighted snapshot metrics remain useful for discrimination/calibration,
            # but global Top-K over all historical snapshots is intentionally NOT
            # reported here because the same separation can appear multiple times.
            metric = base.metric_row(
                split_name=spec.name,
                model_name=model_name,
                test_df=test,
                score=score,
            )
            for key in [
                "precision_at_10", "recall_at_10", "lift_at_10",
                "precision_at_20", "recall_at_20", "lift_at_20",
            ]:
                metric.pop(key, None)
            metric["ranking_scope"] = "WEIGHTED_SNAPSHOT_DISCRIMINATION_ONLY"
            snapshot_metrics.append(metric)
            first_touch.append(
                first_touch_metrics(
                    split_name=spec.name,
                    model_name=model_name,
                    test=test,
                    score=score,
                )
            )
            by_landmark.extend(
                landmark_metrics(
                    split_name=spec.name,
                    model_name=model_name,
                    test=test,
                    score=score,
                )
            )

            out = test[
                [GROUP, "codigo_proforma", "codigo_unidad", "codigo_proyecto", DATE,
                 "landmark_day", "horizon_end_at", TARGET]
            ].copy()
            out["split"] = spec.name
            out["model"] = model_name
            out["score"] = score
            predictions.append(out)

    snapshot_df = pd.DataFrame(snapshot_metrics)
    first_df = pd.DataFrame(first_touch)
    landmark_df = pd.DataFrame(by_landmark)
    split_df = pd.DataFrame(split_health)
    pred_df = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()

    snapshot_df.to_csv(output_dir / "snapshot_metrics.csv", index=False, encoding="utf-8-sig")
    first_df.to_csv(output_dir / "first_touch_metrics.csv", index=False, encoding="utf-8-sig")
    landmark_df.to_csv(output_dir / "landmark_metrics.csv", index=False, encoding="utf-8-sig")
    split_df.to_csv(output_dir / "split_health.csv", index=False, encoding="utf-8-sig")
    pred_df.to_csv(output_dir / "predictions.csv", index=False, encoding="utf-8-sig")

    source_health = health_rows[0] if health_rows else {}
    summary = {
        "status": "OK" if not snapshot_df.empty else "NO_VALID_BENCHMARK_SPLIT",
        "source_health": source_health,
        "feature_scope": "STRUCTURAL_TEMPORAL_30D_V1_MATURE_BINARY_BENCHMARK",
        "horizon_maturity_gate": "horizon_end_at <= observed_through",
        "advisor_included": bool(args.include_advisor),
        "interaction_features_certified": False,
        "group_leakage_policy": "test separation_id is removed from train",
        "ranking_policy": (
            "Global snapshot Top-K is prohibited because repeated snapshots can place the same "
            "separation multiple times in the ranking. Use first_touch_metrics for unique-lifecycle "
            "research ranking; daily operational ranking requires a separate daily risk-set backtest."
        ),
        "outputs": [
            "snapshot_metrics.csv",
            "first_touch_metrics.csv",
            "landmark_metrics.csv",
            "split_health.csv",
            "predictions.csv",
        ],
        "interpretation": (
            "Research benchmark only. Promotion requires mature-horizon out-of-time lift, "
            "subgroup stability, daily operational risk-set backtesting and shadow-mode evidence."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("\n=== MATURE SNAPSHOT METRICS ===")
    print(snapshot_df.sort_values(["split", "pr_auc"], ascending=[True, False]).to_string(index=False))
    print("\n=== FIRST-TOUCH UNIQUE-LIFECYCLE METRICS ===")
    print(first_df.sort_values(["split", "pr_auc"], ascending=[True, False]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
