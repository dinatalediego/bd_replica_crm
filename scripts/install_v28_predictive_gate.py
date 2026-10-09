from __future__ import annotations

from pathlib import Path

from forecast_evaluation_v28 import (
    apply_schema,
    backfill_history,
    capture_current,
    export_artifacts,
    predictive_status,
)
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main():
    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        apply_schema(root, conn)
        print("[V2.8] schema: OK")

        backfill = backfill_history(conn)
        print("[V2.8] historical snapshot generation:")
        for r in backfill:
            print(
                f"  {r['source']}: {r['status']} | "
                f"read={r.get('read_rows', 0)} "
                f"inserted={r.get('inserted', 0)} "
                f"skipped={r.get('skipped', 0)}"
            )

        current = capture_current(conn)
        print(
            "[V2.8] current freeze: "
            f"{current['status']} | "
            f"read={current.get('read_rows', 0)} "
            f"inserted={current.get('inserted', 0)}"
        )

        status = predictive_status(conn)

    if status.get("status") != "OK":
        raise SystemExit(f"Predictive status inválido: {status}")

    export_artifacts(root, status)

    gate = status.get("gate") or {}
    print("\n[V2.8] Predictive Gate")
    print(f"  snapshots={status.get('snapshot_rows')}")
    print(f"  gate={gate.get('gate_status')}")
    print(f"  mature_pairs={gate.get('mature_pairs')}")
    print(f"  projects_with_mature={gate.get('projects_with_mature')}")
    print(f"  defensible_cells={gate.get('defensible_cells')}")
    print(f"  WAPE={gate.get('global_wape_pct')}")
    print(f"  Bias={gate.get('global_bias_pct')}")
    print(f"  leakage_safe={gate.get('leakage_safe_pct')}")
    print(f"  reason={gate.get('gate_reason')}")

    print("\n[V2.8] top project×horizon")
    for r in (status.get("performance") or [])[:12]:
        print(
            f"  {r.get('project_key')} H{r.get('horizon')} | "
            f"n={r.get('mature_pairs')} | "
            f"WAPE={r.get('wape_pct')} | "
            f"Bias={r.get('bias_pct')} | "
            f"{r.get('defense_status')}"
        )


if __name__ == "__main__":
    main()
