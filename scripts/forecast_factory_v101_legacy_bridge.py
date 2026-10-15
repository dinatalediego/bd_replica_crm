from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from psycopg.types.json import Jsonb

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SOURCE_SYSTEM = "MEDALLIO_COMMERCIAL_FORECASTING_V97"
TARGET_NAME = "cumulative_sales_units_existing_stock"
TARGET_UNIT = "units"
SEGMENT_KEY = "ALL"
SCOPE = "EXISTING_STOCK_NO_FUTURE_INFLOWS"
MODEL_FAMILY = {
    "mean3": "NAIVE_ROLLING_MEAN",
    "ets": "EXPONENTIAL_SMOOTHING",
    "gmm_analog": "GMM_ANALOG",
    "random_forest": "RANDOM_FOREST",
}


def fetch_dicts(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def rel_exists(cur, name):
    cur.execute("SELECT to_regclass(%s)", (name,))
    return cur.fetchone()[0] is not None


def install(root: Path, conn):
    p = root / "sql" / "121_forecast_factory_v101" / "01_forecast_factory_v101.sql"
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def ensure_legacy_available(cur):
    required = [
        "model_control.commercial_forecast_runs",
        "analytics.commercial_forecast_predictions",
        "analytics.commercial_forecast_outcomes",
    ]
    missing = [r for r in required if not rel_exists(cur, r)]
    if missing:
        raise RuntimeError("Legacy commercial forecasting missing: " + ", ".join(missing))


def ensure_model(cur, model_name):
    version = "commercial_forecasting_v97"
    family = MODEL_FAMILY.get(model_name, "LEGACY_MODEL")
    cur.execute(
        """
        INSERT INTO model_control.forecast_model_registry_v1(
            model_name, model_version, model_family, target_name, owner,
            lifecycle_status, repo_reference, metadata
        )
        VALUES(%s,%s,%s,%s,%s,'DEVELOPMENT',%s,%s)
        ON CONFLICT(model_name,model_version,target_name)
        DO UPDATE SET metadata=EXCLUDED.metadata
        RETURNING model_version_id
        """,
        (
            model_name, version, family, TARGET_NAME,
            "Medallio Forecast Factory",
            "src/replica_cygnus/commercial_forecasting",
            Jsonb({
                "source_system": SOURCE_SYSTEM,
                "legacy_semantics": "cumulative current-stock sales by horizon",
            }),
        )
    )
    return cur.fetchone()[0]


def evidence_class(created_at, origin, evidence_level):
    # Live issued runs can count as strict prospective only when they were emitted
    # before the first forecast month begins. Historical/synthetic-only artifacts
    # remain non-prospective.
    if evidence_level == "SYNTHETIC_ONLY":
        return "BACKTEST"
    first_window_start = origin + __import__("dateutil.relativedelta").relativedelta.relativedelta(months=1)
    created_local_date = created_at.date()
    return "PROSPECTIVE" if created_local_date < first_window_start else "SHADOW"


def bridge_runs(conn):
    with conn.cursor() as cur:
        ensure_legacy_available(cur)

        rows = fetch_dicts(cur, """
            SELECT
                r.run_id::text AS legacy_run_id,
                r.snapshot_id::text AS snapshot_id,
                r.created_at,
                r.manifest,
                r.evidence_level,
                p.model,
                min(p.origin) AS origin,
                count(*) AS prediction_rows
            FROM model_control.commercial_forecast_runs r
            JOIN analytics.commercial_forecast_predictions p USING(run_id)
            GROUP BY
                r.run_id, r.snapshot_id, r.created_at,
                r.manifest, r.evidence_level, p.model
            ORDER BY r.created_at, r.run_id, p.model
        """)

        inserted_runs = 0
        inserted_predictions = 0

        for row in rows:
            legacy_run_id = row["legacy_run_id"]
            model = row["model"]

            cur.execute(
                """
                SELECT canonical_run_id
                FROM model_control.forecast_legacy_run_map_v101
                WHERE source_system=%s AND legacy_run_id=%s AND legacy_model=%s
                """,
                (SOURCE_SYSTEM, legacy_run_id, model)
            )
            exists = cur.fetchone()
            if exists:
                continue

            model_version_id = ensure_model(cur, model)
            manifest = row["manifest"] or {}
            origin = row["origin"]

            # Snapshot panel start is an honest lower bound for observed source data,
            # not a claim that every estimator used every row.
            cur.execute(
                """
                SELECT min((x->>'month')::date)
                FROM features.commercial_forecast_snapshots s,
                     jsonb_array_elements(s.panel) x
                WHERE s.snapshot_id=%s::uuid
                """,
                (row["snapshot_id"],)
            )
            source_panel_start = cur.fetchone()[0] or origin

            git_sha = manifest.get("git_commit") or "legacy-unknown-sha"
            feature_version = "commercial_forecasting_features_v97"
            ev_class = evidence_class(row["created_at"], origin, row["evidence_level"])

            cur.execute(
                """
                INSERT INTO model_control.forecast_run_v1(
                    model_version_id, issued_at, data_cutoff_date,
                    training_start_date, training_end_date,
                    feature_version, dataset_snapshot_id, code_sha,
                    run_status, run_parameters, environment_fingerprint, notes
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'ISSUED',%s,%s,%s)
                RETURNING run_id
                """,
                (
                    model_version_id, row["created_at"], origin,
                    source_panel_start, origin,
                    feature_version, row["snapshot_id"], git_sha,
                    Jsonb({
                        "legacy_run_id": legacy_run_id,
                        "legacy_model": model,
                        "legacy_manifest_config": manifest.get("config"),
                        "training_start_semantics": "SOURCE_PANEL_START_NOT_EXACT_ESTIMATOR_ROW_START",
                    }),
                    Jsonb({
                        "legacy_python": manifest.get("python"),
                        "legacy_libraries": manifest.get("libraries"),
                    }),
                    f"Bridged from {SOURCE_SYSTEM}; evidence_class={ev_class}",
                )
            )
            canonical_run_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO model_control.forecast_legacy_run_map_v101(
                    source_system, legacy_run_id, legacy_model,
                    canonical_model_version_id, canonical_run_id
                )
                VALUES(%s,%s,%s,%s,%s)
                """,
                (SOURCE_SYSTEM, legacy_run_id, model, model_version_id, canonical_run_id)
            )

            # Baseline for every model is mean3 from the SAME issuance/project/horizon.
            preds = fetch_dicts(cur, """
                SELECT
                    p.project,
                    p.origin,
                    p.horizon,
                    p.model,
                    p.prediction,
                    p.lower80,
                    p.upper80,
                    p.is_selected,
                    b.prediction AS naive_prediction,
                    r.created_at,
                    r.evidence_level
                FROM analytics.commercial_forecast_predictions p
                JOIN model_control.commercial_forecast_runs r USING(run_id)
                LEFT JOIN analytics.commercial_forecast_predictions b
                  ON b.run_id=p.run_id
                 AND b.project=p.project
                 AND b.horizon=p.horizon
                 AND b.model='mean3'
                WHERE p.run_id=%s::uuid AND p.model=%s
                ORDER BY p.project,p.horizon
            """, (legacy_run_id, model))

            for p in preds:
                if p["naive_prediction"] is None:
                    # The canonical contract requires an explicit baseline.
                    continue

                from dateutil.relativedelta import relativedelta
                window_start = p["origin"] + relativedelta(months=1)
                window_end = p["origin"] + relativedelta(months=int(p["horizon"]))
                ev_class_row = evidence_class(p["created_at"], p["origin"], p["evidence_level"])

                cur.execute(
                    """
                    INSERT INTO analytics.forecast_prediction_v1(
                        run_id,
                        project_key, target_name, target_unit, segment_key,
                        forecast_for_period, horizon_months,
                        prediction, prediction_lower, prediction_upper, interval_level,
                        naive_method, naive_prediction,
                        evidence_class, prediction_status,
                        maturity_date, issued_at_copy, data_cutoff_date_copy,
                        metadata,
                        origin_period, forecast_window_start, forecast_window_end,
                        aggregation_semantics, scope_semantics,
                        source_system, source_run_ref, source_model_ref
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,
                        %s,%s,
                        %s,%s,%s,0.80,
                        'mean3',%s,
                        %s,'ISSUED',
                        %s,%s,%s,
                        %s,
                        %s,%s,%s,
                        'CUMULATIVE_WINDOW',%s,
                        %s,%s,%s
                    )
                    ON CONFLICT(
                        run_id,project_key,target_name,segment_key,
                        forecast_for_period,horizon_months
                    ) DO NOTHING
                    """,
                    (
                        canonical_run_id,
                        p["project"], TARGET_NAME, TARGET_UNIT, SEGMENT_KEY,
                        window_end, int(p["horizon"]),
                        p["prediction"], p["lower80"], p["upper80"],
                        p["naive_prediction"],
                        ev_class_row,
                        window_end, p["created_at"], p["origin"],
                        Jsonb({
                            "is_selected": bool(p["is_selected"]),
                            "legacy_semantics": "cumulative sales of current stock from origin through horizon",
                            "interval_status": "AVAILABLE" if p["lower80"] is not None and p["upper80"] is not None else "INSUFFICIENT_TEMPORAL_SUPPORT",
                        }),
                        p["origin"], window_start, window_end,
                        SCOPE,
                        SOURCE_SYSTEM, legacy_run_id, model,
                    )
                )
                inserted_predictions += cur.rowcount

            inserted_runs += 1

        # Bridge mature legacy outcomes into the cumulative-window actual ledger.
        outcomes = fetch_dicts(cur, """
            SELECT
                o.run_id::text AS legacy_run_id,
                o.project,
                o.horizon,
                o.model,
                o.outcome_snapshot_id::text AS outcome_snapshot_id,
                o.actual,
                o.eligible_scope,
                o.eligibility_reason,
                o.measured_at,
                p.origin
            FROM analytics.commercial_forecast_outcomes o
            JOIN analytics.commercial_forecast_predictions p
              USING(run_id,project,horizon,model)
            ORDER BY o.measured_at,o.run_id,o.project,o.horizon,o.model
        """)

        inserted_actuals = 0
        from dateutil.relativedelta import relativedelta
        for o in outcomes:
            window_start = o["origin"] + relativedelta(months=1)
            window_end = o["origin"] + relativedelta(months=int(o["horizon"]))
            cur.execute(
                """
                INSERT INTO analytics.forecast_actual_window_v101(
                    project_key,target_name,target_unit,segment_key,
                    origin_period,forecast_window_start,forecast_window_end,horizon_months,
                    aggregation_semantics,scope_semantics,
                    actual_value,period_complete,compatible_scope,
                    source_system,source_run_ref,source_snapshot_id,source_reference,
                    period_closed_at
                )
                VALUES(
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    'CUMULATIVE_WINDOW',%s,
                    %s,true,%s,
                    %s,%s,%s,%s,
                    %s
                )
                ON CONFLICT(
                    project_key,target_name,segment_key,
                    origin_period,forecast_window_end,
                    aggregation_semantics,scope_semantics
                ) DO NOTHING
                """,
                (
                    o["project"], TARGET_NAME, TARGET_UNIT, SEGMENT_KEY,
                    o["origin"], window_start, window_end, int(o["horizon"]),
                    SCOPE,
                    o["actual"], bool(o["eligible_scope"]),
                    SOURCE_SYSTEM, o["legacy_run_id"], o["outcome_snapshot_id"],
                    o["eligibility_reason"], o["measured_at"],
                )
            )
            inserted_actuals += cur.rowcount

    conn.commit()
    print(
        f"[FORECAST_FACTORY_V101] bridged_runs={inserted_runs} "
        f"predictions={inserted_predictions} actual_windows={inserted_actuals}"
    )


def status(conn):
    with conn.cursor() as cur:
        summary = fetch_dicts(cur, """
            SELECT
                evidence_class,
                aggregation_semantics,
                count(*) AS predictions,
                count(*) FILTER (
                    WHERE prediction_lower IS NULL OR prediction_upper IS NULL
                ) AS interval_incubating
            FROM analytics.forecast_prediction_v1
            GROUP BY evidence_class,aggregation_semantics
            ORDER BY evidence_class,aggregation_semantics
        """)
        perf = fetch_dicts(cur, """
            SELECT defendability_status,count(*) AS cells
            FROM analytics.v_forecast_defendability_v101
            GROUP BY defendability_status
            ORDER BY defendability_status
        """)
        maps = fetch_dicts(cur, """
            SELECT legacy_model,count(*) AS canonical_runs
            FROM model_control.forecast_legacy_run_map_v101
            GROUP BY legacy_model
            ORDER BY legacy_model
        """)

    print("[FORECAST_FACTORY_V101] Bridge map")
    if not maps:
        print("  no bridged runs")
    for r in maps:
        print(f"  {r['legacy_model']}={r['canonical_runs']}")

    print("[FORECAST_FACTORY_V101] Predictions")
    if not summary:
        print("  no canonical predictions")
    for r in summary:
        print(
            f"  {r['evidence_class']} | {r['aggregation_semantics']} | "
            f"predictions={r['predictions']} | interval_incubating={r['interval_incubating']}"
        )

    print("[FORECAST_FACTORY_V101] Defendability")
    if not perf:
        print("  no mature canonical cells")
    for r in perf:
        print(f"  {r['defendability_status']}={r['cells']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command", nargs="?",
        choices=["install","bridge","status"],
        default="status"
    )
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[FORECAST_FACTORY_V101] schema installed.")
            status(conn)
        elif args.command == "bridge":
            bridge_runs(conn)
            status(conn)
        else:
            status(conn)


if __name__ == "__main__":
    main()
