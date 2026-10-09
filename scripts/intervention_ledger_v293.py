from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

VERSION = "2.9.3"


def relation_exists(cur, rel):
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def fetch_dicts(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(cur, sql, params=None):
    rows = fetch_dicts(cur, sql, params)
    return rows[0] if rows else None


def install_schema(root: Path, conn):
    required = [
        "decision_intelligence.project_active_contract_v292",
        "analytics.v_project_schedule_context_v2921",
    ]
    with conn.cursor() as cur:
        missing = [r for r in required if not relation_exists(cur, r)]
        if missing:
            raise RuntimeError(
                "Faltan prerrequisitos: " + ", ".join(missing)
            )

        sql_path = (
            root / "sql" / "112_action_execution_evidence"
            / "01_action_execution_evidence.sql"
        )
        cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def bootstrap(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT decision_intelligence.bootstrap_active_interventions_v293()"
        )
        n = int(cur.fetchone()[0])
    conn.commit()
    print(f"[V2.9.3] intervention bootstrap inserted={n}")


def intervention(cur, project):
    row = fetch_one(
        cur,
        """
        SELECT *
        FROM decision_intelligence.intervention_ledger_v293
        WHERE project_key=%s
          AND execution_status <> 'CANCELLED'
        ORDER BY created_at DESC, intervention_id DESC
        LIMIT 1
        """,
        (project,)
    )
    if not row:
        raise ValueError(
            f"{project}: no intervention ledger. Run bootstrap/install first."
        )
    return row


def add_event(
    conn, project, event_type, actor, note,
    effective_date=None, payload=None, material=False,
    new_status=None
):
    payload = payload or {}
    with conn.cursor() as cur:
        i = intervention(cur, project)
        before_state = {
            "execution_status": i["execution_status"],
            "planned_start_date": i["planned_start_date"],
            "actual_start_date": i["actual_start_date"],
            "actual_end_date": i["actual_end_date"],
            "current_scope": i["current_scope"],
            "actual_action_cost": i["actual_action_cost"],
        }

        if new_status:
            allowed = ["SCHEDULED","STARTED","IMPLEMENTED","COMPLETED","CANCELLED"]
            if new_status not in allowed:
                raise ValueError(f"Invalid new_status={new_status}")

        cur.execute(
            """
            UPDATE decision_intelligence.intervention_ledger_v293
            SET
                execution_status=coalesce(%s, execution_status),
                actual_start_date=
                    CASE WHEN %s='STARTED'
                         THEN coalesce(actual_start_date, %s::date)
                         ELSE actual_start_date END,
                actual_end_date=
                    CASE WHEN %s='COMPLETED'
                         THEN coalesce(actual_end_date, %s::date)
                         ELSE actual_end_date END,
                material_change_count=material_change_count + %s,
                last_event_at=now(),
                last_event_type=%s,
                updated_at=now()
            WHERE intervention_id=%s
            RETURNING *
            """,
            (
                new_status,
                new_status, effective_date,
                new_status, effective_date,
                1 if material else 0,
                event_type,
                i["intervention_id"],
            )
        )
        after = cur.fetchone()
        cols = [d.name for d in cur.description]
        after_state_row = dict(zip(cols, after))

        after_state = {
            "execution_status": after_state_row["execution_status"],
            "planned_start_date": after_state_row["planned_start_date"],
            "actual_start_date": after_state_row["actual_start_date"],
            "actual_end_date": after_state_row["actual_end_date"],
            "current_scope": after_state_row["current_scope"],
            "actual_action_cost": after_state_row["actual_action_cost"],
        }

        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_event_v293(
                intervention_id, contract_id, project_key,
                event_type, effective_date, actor, note,
                before_state, after_state, event_payload,
                is_material_change
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                event_type, effective_date, actor, note,
                json.dumps(before_state, ensure_ascii=False, default=str),
                json.dumps(after_state, ensure_ascii=False, default=str),
                json.dumps(payload, ensure_ascii=False, default=str),
                material,
            )
        )

    conn.commit()
    print(
        f"[V2.9.3] {project} event={event_type} "
        f"status={new_status or i['execution_status']}"
    )


def set_scope(conn, project, actor, scope_file, reason):
    p = Path(scope_file)
    payload = json.loads(p.read_text(encoding="utf-8"))

    with conn.cursor() as cur:
        i = intervention(cur, project)
        before_scope = i.get("current_scope") or {}

        cur.execute(
            """
            UPDATE decision_intelligence.intervention_ledger_v293
            SET
                current_scope=%s::jsonb,
                material_change_count=material_change_count+1,
                last_event_at=now(),
                last_event_type='SCOPE_CHANGED',
                updated_at=now()
            WHERE intervention_id=%s
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                i["intervention_id"],
            )
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_event_v293(
                intervention_id, contract_id, project_key,
                event_type, actor, note,
                before_state, after_state, event_payload,
                is_material_change
            )
            VALUES(%s,%s,%s,'SCOPE_CHANGED',%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,true)
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                actor, reason,
                json.dumps({"scope": before_scope}, ensure_ascii=False, default=str),
                json.dumps({"scope": payload}, ensure_ascii=False, default=str),
                json.dumps({"reason": reason}, ensure_ascii=False),
            )
        )

    conn.commit()
    print(f"[V2.9.3] {project} scope changed and evidenced.")


def record_cost(conn, project, actor, amount, category, cost_date, source_reference=None, note=None, actual=True):
    if amount < 0:
        raise ValueError("amount cannot be negative")

    with conn.cursor() as cur:
        i = intervention(cur, project)

        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_cost_v293(
                intervention_id, contract_id, project_key,
                cost_date, cost_category, amount, currency,
                is_actual, source_reference, note, recorded_by
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                cost_date, category, amount, i["currency"],
                actual, source_reference, note, actor
            )
        )

        cur.execute(
            """
            SELECT coalesce(sum(amount),0)
            FROM decision_intelligence.intervention_cost_v293
            WHERE intervention_id=%s
              AND is_actual=true
            """,
            (i["intervention_id"],)
        )
        actual_total = cur.fetchone()[0]

        cur.execute(
            """
            UPDATE decision_intelligence.intervention_ledger_v293
            SET
                actual_action_cost=%s,
                last_event_at=now(),
                last_event_type='COST_RECORDED',
                updated_at=now()
            WHERE intervention_id=%s
            """,
            (actual_total, i["intervention_id"])
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_event_v293(
                intervention_id, contract_id, project_key,
                event_type, effective_date, actor, note,
                event_payload, is_material_change
            )
            VALUES(%s,%s,%s,'COST_RECORDED',%s,%s,%s,%s::jsonb,false)
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                cost_date, actor, note,
                json.dumps({
                    "cost_category": category,
                    "amount": amount,
                    "is_actual": actual,
                    "source_reference": source_reference,
                    "actual_total": float(actual_total),
                }, ensure_ascii=False)
            )
        )

    conn.commit()
    print(f"[V2.9.3] {project} cost recorded | actual_total={actual_total}")


def attach_evidence(conn, project, actor, evidence_type, source_reference, note=None):
    digest = hashlib.sha256(
        f"{project}|{evidence_type}|{source_reference}|{note or ''}".encode("utf-8")
    ).hexdigest()

    with conn.cursor() as cur:
        i = intervention(cur, project)
        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_evidence_v293(
                intervention_id, contract_id, project_key,
                evidence_type, source_reference, evidence_note,
                evidence_hash, recorded_by
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING evidence_id
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                evidence_type, source_reference, note,
                digest, actor
            )
        )
        evidence_id = cur.fetchone()[0]

        cur.execute(
            """
            UPDATE decision_intelligence.intervention_ledger_v293
            SET
                evidence_count=evidence_count+1,
                last_event_at=now(),
                last_event_type='EVIDENCE_ATTACHED',
                updated_at=now()
            WHERE intervention_id=%s
            """,
            (i["intervention_id"],)
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.intervention_event_v293(
                intervention_id, contract_id, project_key,
                event_type, actor, note, event_payload,
                is_material_change
            )
            VALUES(%s,%s,%s,'EVIDENCE_ATTACHED',%s,%s,%s::jsonb,false)
            """,
            (
                i["intervention_id"], i["contract_id"], project,
                actor, note,
                json.dumps({
                    "evidence_id": evidence_id,
                    "evidence_type": evidence_type,
                    "source_reference": source_reference,
                }, ensure_ascii=False)
            )
        )

    conn.commit()
    print(f"[V2.9.3] {project} evidence_id={evidence_id} attached.")


def export_monitoring(root: Path, conn):
    out = root / "artifacts" / "intervention_monitoring_v293"
    out.mkdir(parents=True, exist_ok=True)

    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_pbi_ai_control_tower_v293
            ORDER BY project_key
            """
        )
        interventions = fetch_dicts(
            cur,
            """
            SELECT *
            FROM decision_intelligence.v_intervention_monitoring_v293
            ORDER BY project_key
            """
        )

    (out / "control_tower.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    (out / "interventions.json").write_text(
        json.dumps(interventions, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )

    md = [
        "# Medallio v2.9.3 — Action Execution Evidence",
        "",
        "| Project | Need now | Execution | Execution health | Outcome SLA | Evidence | Cost |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for r in rows:
        md.append(
            f"| {r.get('project_key')} | {r.get('what_needs_me_now')} | "
            f"{r.get('execution_status') or ''} | {r.get('execution_health') or ''} | "
            f"{r.get('outcome_sla_status') or ''} | {r.get('evidence_count') or 0} | "
            f"{r.get('actual_action_cost') or 0} |"
        )
    (out / "control_tower.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def status(root: Path, conn):
    export_monitoring(root, conn)
    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT
                project_key, intervention_code,
                execution_status, execution_health,
                actual_start_date, actual_end_date,
                evidence_count, material_change_count,
                actual_action_cost,
                outcome_sla_status, outcome_due_date,
                days_to_outcome_due
            FROM decision_intelligence.v_intervention_monitoring_v293
            ORDER BY project_key
            """
        )

    print(f"[V2.9.3] interventions={len(rows)}")
    for r in rows:
        print(
            f"  {r['project_key']} | execution={r['execution_status']} | "
            f"health={r['execution_health']} | evidence={r['evidence_count']} | "
            f"changes={r['material_change_count']} | "
            f"cost={r['actual_action_cost']} | "
            f"outcome_sla={r['outcome_sla_status']} | "
            f"outcome_due={r['outcome_due_date']}"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command", nargs="?",
        choices=[
            "install","bootstrap","status",
            "start","implemented","complete","cancel",
            "scope-change","record-cost","attach-evidence"
        ],
        default="status"
    )
    p.add_argument("--project")
    p.add_argument("--actor")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--file")
    p.add_argument("--reason")
    p.add_argument("--amount", type=float)
    p.add_argument("--category")
    p.add_argument("--source-reference")
    p.add_argument("--evidence-type")
    p.add_argument("--planned", action="store_true")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install_schema(root, conn)
            bootstrap(conn)
            status(root, conn)
            return

        if args.command == "bootstrap":
            bootstrap(conn)
            status(root, conn)
            return

        if args.command == "status":
            status(root, conn)
            return

        if args.command in {"start","implemented","complete","cancel"}:
            if not args.project or not args.actor:
                raise SystemExit("--project and --actor are required")

            if args.command in {"start","complete"} and not args.date:
                raise SystemExit("--date YYYY-MM-DD is required")

            event_map = {
                "start": ("STARTED","STARTED"),
                "implemented": ("IMPLEMENTED","IMPLEMENTED"),
                "complete": ("COMPLETED","COMPLETED"),
                "cancel": ("CANCELLED","CANCELLED"),
            }
            event_type, new_status = event_map[args.command]
            add_event(
                conn, args.project, event_type, args.actor,
                args.note or args.reason,
                effective_date=args.date,
                payload={},
                material=(args.command == "cancel"),
                new_status=new_status
            )
            status(root, conn)
            return

        if args.command == "scope-change":
            if not all([args.project, args.actor, args.file, args.reason]):
                raise SystemExit("--project --actor --file --reason are required")
            set_scope(conn, args.project, args.actor, args.file, args.reason)
            status(root, conn)
            return

        if args.command == "record-cost":
            if not all([args.project, args.actor, args.date, args.category]) or args.amount is None:
                raise SystemExit("--project --actor --date --category --amount are required")
            record_cost(
                conn, args.project, args.actor, args.amount,
                args.category, args.date,
                source_reference=args.source_reference,
                note=args.note,
                actual=not args.planned
            )
            status(root, conn)
            return

        if args.command == "attach-evidence":
            if not all([args.project, args.actor, args.evidence_type, args.source_reference]):
                raise SystemExit("--project --actor --evidence-type --source-reference are required")
            attach_evidence(
                conn, args.project, args.actor,
                args.evidence_type, args.source_reference,
                note=args.note
            )
            status(root, conn)
            return


if __name__ == "__main__":
    main()
