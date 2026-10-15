from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def fetch_dicts(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def relation_exists(cur, rel):
    cur.execute('SELECT to_regclass(%s)', (rel,))
    return cur.fetchone()[0] is not None


def install(root, conn):
    sql_path = root/'sql'/'107_pre_maturity_control'/'01_pre_maturity_control.sql'
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding='utf-8'), prepare=False)
    conn.commit()


def status(conn):
    with conn.cursor() as cur:
        readiness = fetch_dicts(cur, 'SELECT * FROM analytics.v_predictive_pre_maturity_readiness_v284')
        execution = fetch_dicts(cur, 'SELECT * FROM decision_intelligence.v_execution_control_tower_v284')
        issue_exceptions = fetch_dicts(cur, """
            SELECT *
            FROM analytics.v_forecast_issue_quality_v284
            WHERE issuance_class <> 'PROSPECTIVE_ELIGIBLE'
               OR pre_maturity_quality_status <> 'OK'
            ORDER BY issued_at DESC, project_key, horizon
            LIMIT 500
        """)
        decision_gaps = fetch_dicts(cur, """
            SELECT *
            FROM decision_intelligence.v_decision_execution_gap_v284
            ORDER BY
                CASE execution_status
                    WHEN 'NEEDS_OWNER' THEN 1
                    WHEN 'NEEDS_DEADLINE' THEN 2
                    WHEN 'NEEDS_ACTION' THEN 3
                    WHEN 'ACTION_IN_PROGRESS' THEN 4
                    WHEN 'WAITING_OUTCOME' THEN 5
                    WHEN 'OUTCOME_IMMATURE' THEN 6
                    ELSE 7
                END,
                decision_ts DESC
            LIMIT 100
        """)
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'readiness': readiness[0] if readiness else {},
        'execution': execution[0] if execution else {},
        'issue_exceptions': issue_exceptions,
        'decision_gaps': decision_gaps,
    }


def export(root, payload):
    out = root/'artifacts'/'medallio_ceo_briefing'
    out.mkdir(parents=True, exist_ok=True)

    (out/'pre_maturity_control_v284.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8'
    )

    def write_csv(name, rows):
        p = out/name
        if not rows:
            p.write_text('', encoding='utf-8')
            return
        with p.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    write_csv('forecast_issue_quality_exceptions_v284.csv', payload['issue_exceptions'])
    write_csv('decision_execution_gap_v284.csv', payload['decision_gaps'])

    try:
        import matplotlib.pyplot as plt
        r = payload['readiness']
        labels = ['Capturados', 'Prospectivos', 'Activos', 'Incubando', 'Evaluados']
        vals = [
            float(r.get('captured_total') or 0),
            float(r.get('prospective_eligible') or 0),
            float(r.get('active_forecast_cells') or 0),
            float(r.get('incubating') or 0),
            float(r.get('evaluated') or 0),
        ]
        fig, ax = plt.subplots(figsize=(10,5.5))
        ax.bar(labels, vals)
        ax.set_title('Predictive Pre-Maturity Control — v2.8.4')
        ax.set_ylabel('Forecasts / celdas')
        for i,v in enumerate(vals): ax.text(i, v, f'{v:,.0f}', ha='center', va='bottom')
        fig.tight_layout(); fig.savefig(out/'07_pre_maturity_control.png', dpi=160); plt.close(fig)
    except Exception:
        pass

    try:
        import matplotlib.pyplot as plt
        e = payload['execution']
        labels = ['Sin acción', 'En ejecución', 'Esperando outcome', 'Aprendizaje completo']
        vals = [
            float(e.get('needs_action') or 0) + float(e.get('needs_deadline') or 0) + float(e.get('needs_owner') or 0),
            float(e.get('action_in_progress') or 0),
            float(e.get('waiting_outcome') or 0) + float(e.get('outcome_immature') or 0),
            float(e.get('learning_complete') or 0),
        ]
        fig, ax = plt.subplots(figsize=(10,5.5))
        ax.bar(labels, vals)
        ax.set_title('Decision → Action → Outcome → Learning')
        ax.set_ylabel('Decisiones gobernadas')
        for i,v in enumerate(vals): ax.text(i, v, f'{v:,.0f}', ha='center', va='bottom')
        fig.tight_layout(); fig.savefig(out/'08_execution_learning_loop.png', dpi=160); plt.close(fig)
    except Exception:
        pass


def main():
    settings = load_settings(); root = Path(settings.project_root)
    with connect_postgres(settings) as conn:
        install(root, conn)
    with connect_postgres(settings) as conn:
        payload = status(conn)
    export(root, payload)

    r = payload['readiness']; e = payload['execution']
    print('[V2.8.4] Predictive pre-maturity readiness')
    print(
        f"  status={r.get('pre_maturity_status')} | captured={r.get('captured_total')} | "
        f"eligible={r.get('prospective_eligible')} | nowcast={r.get('current_period_nowcast')} | "
        f"active={r.get('active_forecast_cells')} | incubating={r.get('incubating')} | "
        f"bench_coverage={r.get('benchmark_coverage_pct')}% | next_maturity={r.get('next_maturity_date')}"
    )
    print(f"  reason={r.get('pre_maturity_reason')}")

    print('[V2.8.4] Decision execution loop')
    print(
        f"  governed={e.get('governed_decisions')} | needs_action={e.get('needs_action')} | "
        f"needs_deadline={e.get('needs_deadline')} | in_progress={e.get('action_in_progress')} | "
        f"outcomes={e.get('outcomes')} | mature_outcomes={e.get('mature_outcomes')} | "
        f"learning_complete={e.get('learning_complete')}"
    )

    print('[V2.8.4] Top execution gaps')
    for d in payload['decision_gaps'][:8]:
        print(
            f"  {d.get('project_key') or 'PORTFOLIO'} | {d.get('execution_status')} | "
            f"owner={d.get('owner')} | deadline={d.get('deadline')} | {d.get('decision_title')}"
        )


if __name__ == '__main__': main()
