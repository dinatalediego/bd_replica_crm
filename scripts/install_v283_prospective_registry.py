from __future__ import annotations

from pathlib import Path

from forecast_evaluation_v28 import (
    capture_prospective_registry,
    refresh_maturity_v283,
    predictive_status,
    export_artifacts,
)
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def main():
    settings = load_settings()
    root = Path(settings.project_root)
    sql_path = (
        root
        / "sql"
        / "106_prospective_forecast_registry"
        / "01_prospective_registry.sql"
    )

    prerequisites = [
        "analytics.comercial_proyecto_mes",
        "analytics.v_commercial_forecast_current",
    ]

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            missing = [rel for rel in prerequisites if not relation_exists(cur, rel)]
            if missing:
                raise SystemExit(f"Faltan prerequisitos v2.8.3: {missing}")
            cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

    print("[V2.8.3] schema: OK")

    with connect_postgres(settings) as conn:
        capture = capture_prospective_registry(
            conn,
            slot="install",
            dry_run=False,
            capture_reason="V283_BOOTSTRAP",
        )
        maturity = refresh_maturity_v283(conn)
        status = predictive_status(conn)

    if status.get("status") != "OK":
        raise SystemExit(status)

    export_artifacts(root, status)

    print(
        "[V2.8.3] prospective registry | "
        f"source_rows={capture.get('source_rows')} | "
        f"candidate_cells={capture.get('candidate_cells')} | "
        f"inserted={capture.get('inserted')} | "
        f"unchanged={capture.get('unchanged')} | "
        f"ambiguous={capture.get('ambiguous_cells')}"
    )
    print(
        "[V2.8.3] maturity | "
        f"new_matured={maturity.get('new_matured')}"
    )

    factory = status.get("factory_summary") or {}
    gate = status.get("gate") or {}

    print(
        "[V2.8.3] factory | "
        f"issued={factory.get('issued_total')} | "
        f"active={factory.get('active_forecast_cells')} | "
        f"incubating={factory.get('incubating')} | "
        f"evaluated={factory.get('evaluated')} | "
        f"next_maturity={factory.get('next_maturity_date')} | "
        f"benchmarked={factory.get('benchmarked_active')}"
    )
    print(
        "[V2.8.3] gate | "
        f"status={gate.get('gate_status')} | "
        f"mature_pairs={gate.get('mature_pairs')} | "
        f"WAPE={gate.get('global_wape_pct')} | "
        f"naive_WAPE={gate.get('naive_wape_pct')} | "
        f"skill={gate.get('skill_vs_naive_pct')} | "
        f"reason={gate.get('gate_reason')}"
    )


if __name__ == "__main__":
    main()
