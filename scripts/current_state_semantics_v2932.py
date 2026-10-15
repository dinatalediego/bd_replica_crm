from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def fetch_dicts(cur, sql):
    cur.execute(sql)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def install(root: Path, conn):
    p = root / "sql" / "114_current_state_semantics" / "01_current_state_semantics.sql"
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def status(conn):
    with conn.cursor() as cur:
        current = fetch_dicts(cur, """
            SELECT
                project_key, contract_code, primary_metric,
                metric_semantics_status, execution_status,
                execution_health, outcome_phase_status
            FROM decision_intelligence.v_intervention_current_v2932
            ORDER BY project_key
        """)
        hist = fetch_dicts(cur, """
            SELECT project_key, execution_status, count(*) AS n
            FROM decision_intelligence.v_intervention_monitoring_v293
            GROUP BY project_key, execution_status
            ORDER BY project_key, execution_status
        """)
        kpi = fetch_dicts(cur, "SELECT * FROM analytics.v_ai_control_tower_kpis_v2931")[0]
        issues = fetch_dicts(cur, "SELECT * FROM analytics.v_pbi_contract_semantics_issues_v2931")

    print(
        "[V2.9.3.2] CURRENT KPIs | "
        f"scheduled={kpi['scheduled_interventions']} | "
        f"active_execution={kpi['active_executions']} | "
        f"waiting_outcome={kpi['waiting_outcomes']} | "
        f"mature_outcomes={kpi['mature_outcomes']} | "
        f"metric_issues={kpi['contracts_with_metric_semantics_issue']}"
    )

    print("[V2.9.3.2] CURRENT INTERVENTIONS")
    for r in current:
        print(
            f"  {r['project_key']} | contract={r['contract_code']} | "
            f"metric={r['primary_metric']} | semantics={r['metric_semantics_status']} | "
            f"execution={r['execution_status']} | health={r['execution_health']} | "
            f"outcome={r['outcome_phase_status']}"
        )

    print("[V2.9.3.2] HISTORY RETAINED")
    for r in hist:
        print(f"  {r['project_key']} | {r['execution_status']}={r['n']}")

    if issues:
        print("[V2.9.3.2] CURRENT SEMANTICS ISSUES")
        for r in issues:
            print(f"  {r['project_key']} | {r['primary_metric']} | {r['metric_semantics_status']}")
    else:
        print("[V2.9.3.2] Current metric semantics: OK")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="?", choices=["install","status"], default="status")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[V2.9.3.2] views installed.")
        status(conn)


if __name__ == "__main__":
    main()
