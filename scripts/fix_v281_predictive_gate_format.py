from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def fetch_one_dict(cur, sql):
    cur.execute(sql)
    cols = [d.name for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


def main():
    settings = load_settings()
    root = Path(settings.project_root)
    sql_path = (
        root
        / "sql"
        / "104_predictive_gate_format_hotfix"
        / "01_fix_gate_reason_format.sql"
    )

    if not sql_path.exists():
        raise SystemExit(f"Falta {sql_path}")

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM model_control.forecast_prediction_snapshot"
            )
            snapshots = int(cur.fetchone()[0])

            gate = fetch_one_dict(
                cur,
                "SELECT * FROM analytics.v_forecast_predictive_gate"
            )

            cur.execute(
                """
                SELECT count(*)
                FROM analytics.v_forecast_evaluation_mature
                WHERE eligible_for_operational_scoring
                """
            )
            mature_rows = int(cur.fetchone()[0])

    print("[V2.8.1] Predictive gate format hotfix: OK")
    print(f"[V2.8.1] snapshots={snapshots}")
    print(f"[V2.8.1] mature_evaluable_rows={mature_rows}")
    print(
        "[V2.8.1] gate="
        f"{gate.get('gate_status')} | "
        f"pairs={gate.get('mature_pairs')} | "
        f"projects={gate.get('projects_with_mature')} | "
        f"defensible_cells={gate.get('defensible_cells')} | "
        f"WAPE={gate.get('global_wape_pct')} | "
        f"Bias={gate.get('global_bias_pct')} | "
        f"leakage_safe={gate.get('leakage_safe_pct')}"
    )
    print(f"[V2.8.1] reason={gate.get('gate_reason')}")


if __name__ == "__main__":
    main()
