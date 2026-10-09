from __future__ import annotations

import argparse
import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def rows_as_dicts(cur):
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def export_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["install", "refresh", "status"], nargs="?", default="install")
    args = parser.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)
    contract = root / "sql" / "101_project_growth_state" / "01_contract.sql"

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            if args.command in {"install", "refresh"}:
                # Evolution tables are the physical comparable base. Refresh first.
                cur.execute("SELECT analytics.refresh_evolucion_comercial()")
                cur.execute(contract.read_text(encoding="utf-8"), prepare=False)
                conn.commit()

            cur.execute("""
                SELECT
                    project_key, project_name, snapshot_date, current_period,
                    current_period_partial, latest_complete_period,
                    stock_lanzamiento, stock_units, last_complete_sales_units,
                    ventas_promedio_3m, ventas_promedio_6m,
                    absorption_rate, months_to_zero,
                    target_value, commercial_placed_value, gap_value, stock_value,
                    forecast_units, forecast_wape_pct,
                    attention_score, suggested_action, suggested_owner,
                    suggested_urgency, data_quality_status, evidence_gaps
                FROM analytics.v_project_growth_state
                ORDER BY attention_score DESC, gap_value DESC NULLS LAST, project_key
            """)
            states = rows_as_dicts(cur)

            cur.execute("""
                SELECT
                    project_key, project_name, attention_score, decision, owner,
                    urgency, value_at_stake_soles, value_at_stake_type,
                    confidence_label, why, suggested_outcome_metric,
                    outcome_required, roi_required, decision_level
                FROM decision_intelligence.v_ceo_growth_decision_queue
                ORDER BY attention_score DESC, value_at_stake_soles DESC NULLS LAST
            """)
            actions = rows_as_dicts(cur)

    out = root / "artifacts" / "medallio_ceo_briefing"
    export_csv(out / "project_growth_state_db.csv", states)
    export_csv(out / "ceo_growth_decision_queue.csv", actions)

    print(f"[PROJECT_GROWTH_STATE] proyectos={len(states)}")
    if states:
        complete = sum(r.get("latest_complete_period") is not None for r in states)
        print(f"[PROJECT_GROWTH_STATE] con_mes_completo={complete}/{len(states)}")
        print("[PROJECT_GROWTH_STATE] top:")
        for r in states[:5]:
            print(
                f"  {r['project_key']}: score={r['attention_score']} | "
                f"stock={r['stock_units']} | sales={r['last_complete_sales_units']} | "
                f"gap={r['gap_value']} | action={r['suggested_action']}"
            )

    print(f"[CEO_QUEUE] decisiones={len(actions)}")
    for r in actions[:5]:
        print(f"  {r['project_key']}: {r['decision']} | owner={r['owner']} | urgency={r['urgency']}")


if __name__ == "__main__":
    main()
