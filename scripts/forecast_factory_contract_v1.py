from __future__ import annotations

import argparse
import json
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def fetch_dicts(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def install(root: Path, conn):
    sql_path = (
        root / "sql" / "120_forecast_factory_contract_v1"
        / "01_forecast_factory_contract_v1.sql"
    )
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def status(conn):
    with conn.cursor() as cur:
        models = fetch_dicts(cur, """
            SELECT lifecycle_status, count(*) AS n
            FROM model_control.forecast_model_registry_v1
            GROUP BY lifecycle_status
            ORDER BY lifecycle_status
        """)
        runs = fetch_dicts(cur, """
            SELECT contract_status, count(*) AS n
            FROM model_control.v_forecast_run_contract_compliance_v1
            GROUP BY contract_status
            ORDER BY contract_status
        """)
        maturity = fetch_dicts(cur, """
            SELECT maturity_status, count(*) AS n
            FROM analytics.v_forecast_maturity_clock_v1
            GROUP BY maturity_status
            ORDER BY maturity_status
        """)
        defend = fetch_dicts(cur, """
            SELECT defendability_status, count(*) AS n
            FROM analytics.v_forecast_defendability_v1
            GROUP BY defendability_status
            ORDER BY defendability_status
        """)

    print("[FORECAST_FACTORY_V1] Models")
    for r in models:
        print(f"  {r['lifecycle_status']}={r['n']}")

    print("[FORECAST_FACTORY_V1] Run contract compliance")
    if not runs:
        print("  no runs yet")
    for r in runs:
        print(f"  {r['contract_status']}={r['n']}")

    print("[FORECAST_FACTORY_V1] Maturity")
    if not maturity:
        print("  no predictions yet")
    for r in maturity:
        print(f"  {r['maturity_status']}={r['n']}")

    print("[FORECAST_FACTORY_V1] Defendability")
    if not defend:
        print("  no mature evaluation yet")
    for r in defend:
        print(f"  {r['defendability_status']}={r['n']}")


def validate_run(conn, run_id: int):
    with conn.cursor() as cur:
        rows = fetch_dicts(cur, """
            SELECT *
            FROM model_control.v_forecast_run_contract_compliance_v1
            WHERE run_id=%s
        """, (run_id,))

    if not rows:
        raise SystemExit(f"run_id={run_id} not found")

    r = rows[0]
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    if r["contract_status"] != "PASS":
        raise SystemExit(2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        nargs="?",
        choices=["install", "status", "validate-run"],
        default="status"
    )
    p.add_argument("--run-id", type=int)
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[FORECAST_FACTORY_V1] schema installed.")
            status(conn)
            return

        if args.command == "validate-run":
            if args.run_id is None:
                raise SystemExit("--run-id is required")
            validate_run(conn, args.run_id)
            return

        status(conn)


if __name__ == "__main__":
    main()
