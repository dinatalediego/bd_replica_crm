from __future__ import annotations

from pathlib import Path

from forecast_evaluation_v28 import export_artifacts, predictive_status
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


EXPECTED_PREFIXES = {
    "analytics.v_forecast_evaluation_mature": [
        "forecast_snapshot_id", "source_hash", "source_relation", "capture_mode",
        "run_id", "project_key", "origin_period", "target_period", "horizon",
        "prediction", "actual", "signed_error", "absolute_error", "ape_pct",
        "issued_at", "issuance_evidence", "leakage_safe", "is_selected",
        "model_name", "model_version", "stock_at_origin", "target_sales",
        "expected_shortfall", "actual_stock_open", "actual_stock_close",
        "actual_absorption_rate", "mes_vida", "actual_cutoff_date",
        "mature_for_evaluation", "eligible_for_operational_scoring"
    ],
    "analytics.v_forecast_predictive_gate": [
        "cells", "defensible_cells", "projects_with_mature", "mature_pairs",
        "leakage_safe_pairs", "global_wape_pct", "global_bias_pct",
        "leakage_safe_pct", "gate_status", "gate_score", "gate_reason"
    ],
}


def current_columns(cur, relation: str) -> list[str]:
    schema, name = relation.split(".", 1)
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, name),
    )
    return [r[0] for r in cur.fetchall()]


def main():
    settings = load_settings()
    root = Path(settings.project_root)
    sql_file = (
        root
        / "sql"
        / "105_predictive_evidence_calibration"
        / "01_calibrate_predictive_evidence.sql"
    )

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            print("[V2.8.2.1] View compatibility preflight")
            for rel, expected in EXPECTED_PREFIXES.items():
                current = current_columns(cur, rel)
                if current:
                    prefix = current[:len(expected)]
                    print(
                        f"  {rel}: current_cols={len(current)} | "
                        f"prefix_compatible={prefix == expected}"
                    )
                    if prefix != expected:
                        print(f"    current prefix : {prefix}")
                        print(f"    expected prefix: {expected}")
                        raise SystemExit(
                            f"Contrato inesperado en {rel}; no se aplicó ningún DROP."
                        )
                else:
                    print(f"  {rel}: no existe todavía")

            cur.execute(sql_file.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

    with connect_postgres(settings) as conn:
        status = predictive_status(conn)

    if status.get("status") != "OK":
        raise SystemExit(status)

    export_artifacts(root, status)
    gate = status.get("gate") or {}

    print("\n[V2.8.2.1] Calibration applied safely")
    print(
        "  gate="
        f"{gate.get('gate_status')} | "
        f"pairs={gate.get('mature_pairs')} | "
        f"projects={gate.get('projects_with_mature')} | "
        f"defensible={gate.get('defensible_cells')} | "
        f"WAPE={gate.get('global_wape_pct')} | "
        f"Bias={gate.get('global_bias_pct')}"
    )
    print(f"  reason={gate.get('gate_reason')}")
    print(
        "  inventory | "
        f"snapshots={gate.get('snapshot_rows')} | "
        f"issued={gate.get('issued_evidence_rows')} | "
        f"backtest_only={gate.get('backtest_only_rows')} | "
        f"unverified={gate.get('unverified_rows')}"
    )

    print("\n[V2.8.2.1] Source diagnostic")
    for r in (status.get("source_diagnostic") or [])[:10]:
        print(
            f"  {r.get('source_relation')} | "
            f"class={r.get('evidence_class')} | "
            f"rows={r.get('matched_rows')} | "
            f"cells={r.get('distinct_cells')} | "
            f"pred/actual={r.get('prediction_to_actual_ratio')} | "
            f"WAPE={r.get('diagnostic_wape_pct')} | "
            f"Bias={r.get('diagnostic_bias_pct')}"
        )

    print("\n[V2.8.2.1] Grain audit")
    for r in (status.get("evidence_audit") or [])[:10]:
        print(
            f"  {r.get('source_relation')} | "
            f"class={r.get('evidence_class')} | "
            f"rows={r.get('snapshot_rows')} | "
            f"cells={r.get('distinct_cells')} | "
            f"rows/cell={r.get('rows_per_cell')} | "
            f"selection={r.get('selection_evidence')} | "
            f"issuance={r.get('issuance_evidence')}"
        )


if __name__ == "__main__":
    main()
