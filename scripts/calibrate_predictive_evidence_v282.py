from __future__ import annotations

from pathlib import Path

from forecast_evaluation_v28 import export_artifacts, predictive_status
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main():
    settings = load_settings()
    root = Path(settings.project_root)
    sql_path = (
        root
        / "sql"
        / "105_predictive_evidence_calibration"
        / "01_calibrate_predictive_evidence.sql"
    )

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

    with connect_postgres(settings) as conn:
        status = predictive_status(conn)

    if status.get("status") != "OK":
        raise SystemExit(status)

    export_artifacts(root, status)

    gate = status.get("gate") or {}
    print("[V2.8.2] Predictive Evidence Calibration: OK")
    print(
        "[V2.8.2] gate="
        f"{gate.get('gate_status')} | "
        f"pairs={gate.get('mature_pairs')} | "
        f"projects={gate.get('projects_with_mature')} | "
        f"defensible_cells={gate.get('defensible_cells')} | "
        f"WAPE={gate.get('global_wape_pct')} | "
        f"Bias={gate.get('global_bias_pct')}"
    )
    print(f"[V2.8.2] reason={gate.get('gate_reason')}")
    print(
        "[V2.8.2] inventory | "
        f"snapshots={gate.get('snapshot_rows')} | "
        f"issued={gate.get('issued_evidence_rows')} | "
        f"backtest_only={gate.get('backtest_only_rows')} | "
        f"unverified={gate.get('unverified_rows')}"
    )

    print("\n[V2.8.2] Source diagnostic")
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

    print("\n[V2.8.2] Snapshot grain audit")
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
