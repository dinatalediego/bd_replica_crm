from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def relation_exists(cur, rel):
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def fetch_dicts(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def install(root: Path, conn):
    req = [
        "decision_intelligence.intervention_ledger_v293",
        "analytics.v_pbi_ai_control_tower_v293",
    ]
    with conn.cursor() as cur:
        missing = [x for x in req if not relation_exists(cur, x)]
        if missing:
            raise RuntimeError("Missing prerequisites: " + ", ".join(missing))
        p = root / "sql" / "113_monitoring_semantics" / "01_monitoring_semantics.sql"
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def status(conn):
    with conn.cursor() as cur:
        kpis = fetch_dicts(
            cur,
            "SELECT * FROM analytics.v_ai_control_tower_kpis_v2931"
        )[0]
        interventions = fetch_dicts(
            cur,
            """
            SELECT
                project_key, primary_metric, metric_semantics_status,
                execution_status, execution_health,
                outcome_phase_status, contract_sla_status,
                outcome_due_date
            FROM decision_intelligence.v_intervention_monitoring_v293
            ORDER BY project_key
            """
        )
        issues = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_pbi_contract_semantics_issues_v2931
            ORDER BY project_key
            """
        )

    print(
        "[V2.9.3.1] KPIs | "
        f"scheduled={kpis['scheduled_interventions']} | "
        f"active_execution={kpis['active_executions']} | "
        f"waiting_outcome={kpis['waiting_outcomes']} | "
        f"mature_outcomes={kpis['mature_outcomes']} | "
        f"metric_issues={kpis['contracts_with_metric_semantics_issue']}"
    )

    for r in interventions:
        print(
            f"  {r['project_key']} | metric={r['primary_metric']} | "
            f"metric_semantics={r['metric_semantics_status']} | "
            f"execution={r['execution_status']} | health={r['execution_health']} | "
            f"outcome_phase={r['outcome_phase_status']} | "
            f"contract_sla={r['contract_sla_status']} | due={r['outcome_due_date']}"
        )

    if issues:
        print("[V2.9.3.1] CONTRACT SEMANTICS ISSUES:")
        for r in issues:
            print(
                f"  {r['project_key']} | primary_metric={r['primary_metric']} | "
                f"{r['recommended_action']}"
            )
    else:
        print("[V2.9.3.1] Metric semantics: OK")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="?", choices=["install","status"], default="status")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[V2.9.3.1] schema/views installed.")
        status(conn)


if __name__ == "__main__":
    main()
