from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


VERSION = "2.9.2"


def jd(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=jd).encode("utf-8")
    ).hexdigest()


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def fetch_dicts(cur, sql: str, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(cur, sql: str, params=None):
    rows = fetch_dicts(cur, sql, params)
    return rows[0] if rows else None


def install_schema(root: Path, conn):
    prereq = "decision_intelligence.project_decision_contract_draft_v291"
    with conn.cursor() as cur:
        if not relation_exists(cur, prereq):
            raise RuntimeError(
                f"Falta {prereq}. Instala v2.9.1 antes de v2.9.2."
            )

    sql_path = (
        root
        / "sql"
        / "110_human_approval_contract_activation"
        / "01_contract_activation_outcome_sla.sql"
    )
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def route_config(root: Path) -> dict:
    p = root / "config" / "contract_routes_v292.json"
    return json.loads(p.read_text(encoding="utf-8"))


def sync_routes(root: Path, conn):
    cfg = route_config(root)
    with conn.cursor() as cur:
        for project_key, r in cfg["projects"].items():
            cur.execute(
                """
                INSERT INTO decision_intelligence.project_contract_route_v292(
                    project_key, route_status, activation_eligible,
                    required_gate, route_reason, updated_at
                )
                VALUES(%s,%s,%s,%s,%s,now())
                ON CONFLICT(project_key) DO UPDATE SET
                    route_status = EXCLUDED.route_status,
                    activation_eligible = EXCLUDED.activation_eligible,
                    required_gate = EXCLUDED.required_gate,
                    route_reason = EXCLUDED.route_reason,
                    updated_at = now()
                """,
                (
                    project_key,
                    r["route_status"],
                    bool(r["activation_eligible"]),
                    r.get("required_gate"),
                    r.get("reason"),
                )
            )
    conn.commit()


def latest_draft(cur, project_key: str):
    return fetch_one(
        cur,
        """
        SELECT *
        FROM decision_intelligence.project_decision_contract_draft_v291
        WHERE project_key = %s
        ORDER BY created_at DESC, draft_id DESC
        LIMIT 1
        """,
        (project_key,)
    )


def route_row(cur, project_key: str):
    return fetch_one(
        cur,
        """
        SELECT *
        FROM decision_intelligence.project_contract_route_v292
        WHERE project_key = %s
        """,
        (project_key,)
    )


def approval_template(cur, project_key: str) -> dict:
    route = route_row(cur, project_key)
    if not route:
        raise RuntimeError(f"{project_key}: no existe route v2.9.2.")

    draft = latest_draft(cur, project_key)
    if not draft:
        raise RuntimeError(f"{project_key}: no existe draft v2.9.1.")

    baseline = draft.get("baseline_json") or {}
    if isinstance(baseline, str):
        baseline = json.loads(baseline)

    secondary = draft.get("secondary_metrics") or []
    if isinstance(secondary, str):
        secondary = json.loads(secondary)

    required = draft.get("required_before_execution") or []
    if isinstance(required, str):
        required = json.loads(required)

    return {
        "version": VERSION,
        "project_key": project_key,
        "project_name": draft.get("project_name"),
        "draft_id": draft["draft_id"],
        "route_status": route["route_status"],
        "activation_eligible": bool(route["activation_eligible"]),
        "required_gate": route.get("required_gate"),

        "hypothesis": draft.get("hypothesis"),
        "proposed_action": draft.get("proposed_action"),

        "owner_confirmed": draft.get("owner_suggested"),
        "deadline": None,

        "primary_metric": draft.get("primary_metric"),
        "secondary_metrics": secondary,

        "baseline": baseline,
        "success_criterion": None,

        "outcome_window_days": None,
        "outcome_capture_method": None,

        "action_cost": draft.get("action_cost"),
        "currency": "PEN",
        "roi_measurement_plan": None,

        "approved_by": None,
        "approval_note": None,

        "required_before_execution": required,
        "human_review_required": True,
        "warning": (
            "Do not approve until deadline, success criterion, outcome window, "
            "capture method and ROI plan are explicitly defined."
        ),
    }


def write_approval_templates(root: Path, conn):
    out = root / "artifacts" / "contract_activation_v292"
    out.mkdir(parents=True, exist_ok=True)

    with conn.cursor() as cur:
        routes = fetch_dicts(
            cur,
            """
            SELECT *
            FROM decision_intelligence.project_contract_route_v292
            ORDER BY project_key
            """
        )

        for r in routes:
            project_key = r["project_key"]
            folder = out / project_key
            folder.mkdir(parents=True, exist_ok=True)

            if r["activation_eligible"]:
                payload = approval_template(cur, project_key)
                p = folder / "approval_template.json"
                # Never overwrite a user's partially completed template.
                if not p.exists():
                    p.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2, default=jd),
                        encoding="utf-8"
                    )
            else:
                (folder / "route_status.json").write_text(
                    json.dumps(
                        {
                            "project_key": project_key,
                            "route_status": r["route_status"],
                            "activation_eligible": False,
                            "required_gate": r.get("required_gate"),
                            "reason": r.get("route_reason"),
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=jd,
                    ),
                    encoding="utf-8"
                )


def parse_date(v: str, field: str) -> date:
    try:
        return date.fromisoformat(v)
    except Exception:
        raise ValueError(f"{field} debe tener formato YYYY-MM-DD.")


def validate_approval_payload(cur, payload: dict) -> tuple[dict, dict, dict]:
    project_key = str(payload.get("project_key") or "").strip()
    if not project_key:
        raise ValueError("Falta project_key.")

    route = route_row(cur, project_key)
    if not route:
        raise ValueError(f"{project_key}: no existe route.")

    if not route["activation_eligible"]:
        raise ValueError(
            f"{project_key}: route={route['route_status']}; "
            "v2.9.2 no permite aprobación para activación."
        )

    if project_key not in {"MD", "MT"}:
        raise ValueError(
            f"{project_key}: sólo MD y MT son candidatos a activación en v2.9.2."
        )

    draft = latest_draft(cur, project_key)
    if not draft:
        raise ValueError(f"{project_key}: no existe draft.")

    if int(payload.get("draft_id") or 0) != int(draft["draft_id"]):
        raise ValueError(
            f"{project_key}: approval_template apunta a draft_id={payload.get('draft_id')} "
            f"pero el latest draft es {draft['draft_id']}. Regenera/revisa el template."
        )

    required_text = {
        "owner_confirmed": payload.get("owner_confirmed"),
        "primary_metric": payload.get("primary_metric"),
        "success_criterion": payload.get("success_criterion"),
        "outcome_capture_method": payload.get("outcome_capture_method"),
        "roi_measurement_plan": payload.get("roi_measurement_plan"),
        "approved_by": payload.get("approved_by"),
    }
    missing = [
        k for k, v in required_text.items()
        if v is None or not str(v).strip()
    ]
    if missing:
        raise ValueError(f"Faltan campos humanos obligatorios: {missing}")

    deadline_raw = payload.get("deadline")
    if not deadline_raw:
        raise ValueError("Falta deadline.")
    deadline = parse_date(str(deadline_raw), "deadline")

    if deadline < date.today():
        raise ValueError("deadline no puede estar en el pasado.")

    try:
        window = int(payload.get("outcome_window_days"))
    except Exception:
        raise ValueError("outcome_window_days debe ser entero.")

    if window < 1 or window > 730:
        raise ValueError("outcome_window_days debe estar entre 1 y 730.")

    criterion = str(payload["success_criterion"]).strip()
    if criterion.upper() in {
        "TO_DEFINE_EX_ANTE",
        "TBD",
        "PENDING",
        "NONE",
        "NULL",
    }:
        raise ValueError(
            "success_criterion debe estar definido ex ante; no puede ser placeholder."
        )

    action_cost = payload.get("action_cost")
    if action_cost is not None:
        try:
            action_cost = float(action_cost)
        except Exception:
            raise ValueError("action_cost debe ser numérico o null.")
        if action_cost < 0:
            raise ValueError("action_cost no puede ser negativo.")

    baseline = payload.get("baseline")
    if not isinstance(baseline, dict) or not baseline:
        raise ValueError("baseline debe ser un objeto JSON no vacío.")

    draft_baseline = draft.get("baseline_json") or {}
    if isinstance(draft_baseline, str):
        draft_baseline = json.loads(draft_baseline)

    if stable_hash(baseline) != stable_hash(draft_baseline):
        raise ValueError(
            "El baseline del approval_template cambió respecto al draft. "
            "Regenera el draft/contexto si necesitas un nuevo baseline."
        )

    normalized = dict(payload)
    normalized["project_key"] = project_key
    normalized["deadline"] = deadline.isoformat()
    normalized["outcome_window_days"] = window
    normalized["action_cost"] = action_cost
    normalized["baseline_hash"] = stable_hash(baseline)
    return route, draft, normalized


def approve(root: Path, conn, file_path: str):
    p = Path(file_path)
    if not p.is_absolute():
        p = root / p

    payload = json.loads(p.read_text(encoding="utf-8"))

    with conn.cursor() as cur:
        route, draft, normalized = validate_approval_payload(cur, payload)

        cur.execute(
            """
            SELECT contract_id
            FROM decision_intelligence.project_active_contract_v292
            WHERE project_key = %s
              AND status IN ('ACTIVE','WAITING_OUTCOME','OUTCOME_MATURE')
            LIMIT 1
            """,
            (normalized["project_key"],)
        )
        if cur.fetchone():
            raise RuntimeError(
                f"{normalized['project_key']}: ya existe contrato activo."
            )

        cur.execute(
            """
            UPDATE decision_intelligence.project_contract_approval_v292
            SET
                status='REVOKED',
                revoked_at=now(),
                revoked_by=%s,
                revoke_reason='Superseded by a newer human approval'
            WHERE project_key=%s
              AND status='APPROVED_READY'
            """,
            (
                normalized["approved_by"],
                normalized["project_key"],
            )
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_approval_v292(
                draft_id, project_key, project_name,
                approved_by, owner_confirmed, deadline,
                primary_metric, success_criterion,
                outcome_window_days, outcome_capture_method,
                roi_measurement_plan, action_cost, currency,
                baseline_json, baseline_hash,
                approval_payload, status
            )
            VALUES(
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,
                %s,%s,
                %s,%s,%s,
                %s::jsonb,%s,
                %s::jsonb,'APPROVED_READY'
            )
            RETURNING approval_id
            """,
            (
                draft["draft_id"],
                normalized["project_key"],
                draft.get("project_name"),
                normalized["approved_by"],
                normalized["owner_confirmed"],
                normalized["deadline"],
                normalized["primary_metric"],
                normalized["success_criterion"],
                normalized["outcome_window_days"],
                normalized["outcome_capture_method"],
                normalized["roi_measurement_plan"],
                normalized.get("action_cost"),
                normalized.get("currency") or "PEN",
                json.dumps(normalized["baseline"], ensure_ascii=False, default=jd),
                normalized["baseline_hash"],
                json.dumps(normalized, ensure_ascii=False, default=jd),
            )
        )
        approval_id = cur.fetchone()[0]

        cur.execute(
            """
            UPDATE decision_intelligence.project_decision_contract_draft_v291
            SET
                status='APPROVED_READY',
                approved_at=now(),
                approved_by=%s
            WHERE draft_id=%s
            """,
            (normalized["approved_by"], draft["draft_id"])
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_event_v292(
                draft_id, project_key, event_type, actor, payload
            )
            VALUES(%s,%s,'HUMAN_APPROVED',%s,%s::jsonb)
            """,
            (
                draft["draft_id"],
                normalized["project_key"],
                normalized["approved_by"],
                json.dumps(
                    {
                        "approval_id": approval_id,
                        "baseline_hash": normalized["baseline_hash"],
                        "deadline": normalized["deadline"],
                        "primary_metric": normalized["primary_metric"],
                    },
                    ensure_ascii=False,
                ),
            )
        )

    conn.commit()
    print(
        f"[V2.9.2] {normalized['project_key']} APPROVED_READY | "
        f"approval_id={approval_id} | approved_by={normalized['approved_by']}"
    )


def latest_approval(cur, project_key: str):
    return fetch_one(
        cur,
        """
        SELECT *
        FROM decision_intelligence.project_contract_approval_v292
        WHERE project_key=%s
          AND status='APPROVED_READY'
        ORDER BY approved_at DESC, approval_id DESC
        LIMIT 1
        """,
        (project_key,)
    )


def activate(conn, project_key: str, activated_by: str):
    if project_key not in {"MD", "MT"}:
        raise ValueError("v2.9.2 sólo permite activar MD o MT.")

    with conn.cursor() as cur:
        route = route_row(cur, project_key)
        if not route or not route["activation_eligible"]:
            raise ValueError(
                f"{project_key}: no es activation candidate."
            )

        approval = latest_approval(cur, project_key)
        if not approval:
            raise ValueError(
                f"{project_key}: falta human approval APPROVED_READY."
            )

        draft = fetch_one(
            cur,
            """
            SELECT *
            FROM decision_intelligence.project_decision_contract_draft_v291
            WHERE draft_id=%s
            """,
            (approval["draft_id"],)
        )
        if not draft:
            raise RuntimeError("Draft aprobado no existe.")

        cur.execute(
            """
            SELECT contract_id
            FROM decision_intelligence.project_active_contract_v292
            WHERE project_key=%s
              AND status IN ('ACTIVE','WAITING_OUTCOME','OUTCOME_MATURE')
            LIMIT 1
            """,
            (project_key,)
        )
        if cur.fetchone():
            raise RuntimeError(f"{project_key}: ya tiene contrato abierto.")

        secondary = draft.get("secondary_metrics") or []
        if isinstance(secondary, str):
            secondary = json.loads(secondary)

        baseline = approval.get("baseline_json") or {}
        if isinstance(baseline, str):
            baseline = json.loads(baseline)

        contract_code = (
            f"MED-{project_key}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_active_contract_v292(
                contract_code,
                draft_id, approval_id,
                project_key, project_name,
                route_status_at_activation,
                hypothesis, proposed_action,
                owner, deadline,
                primary_metric, secondary_metrics,
                baseline_json, baseline_hash,
                success_criterion,
                outcome_window_days, outcome_due_date,
                action_cost, currency,
                outcome_capture_method, roi_measurement_plan,
                value_at_risk, value_to_capture, evidence_level,
                status, activated_by
            )
            VALUES(
                %s,
                %s,%s,
                %s,%s,
                %s,
                %s,%s,
                %s,%s,
                %s,%s::jsonb,
                %s::jsonb,%s,
                %s,
                %s,(current_date + %s),
                %s,%s,
                %s,%s,
                %s,%s,%s,
                'ACTIVE',%s
            )
            RETURNING contract_id, outcome_due_date
            """,
            (
                contract_code,
                draft["draft_id"],
                approval["approval_id"],
                project_key,
                draft.get("project_name"),
                route["route_status"],
                draft.get("hypothesis"),
                draft.get("proposed_action"),
                approval["owner_confirmed"],
                approval["deadline"],
                approval["primary_metric"],
                json.dumps(secondary, ensure_ascii=False),
                json.dumps(baseline, ensure_ascii=False, default=jd),
                approval["baseline_hash"],
                approval["success_criterion"],
                approval["outcome_window_days"],
                approval["outcome_window_days"],
                approval.get("action_cost"),
                approval.get("currency") or "PEN",
                approval["outcome_capture_method"],
                approval["roi_measurement_plan"],
                draft.get("value_at_risk"),
                draft.get("value_to_capture"),
                draft.get("evidence_level"),
                activated_by,
            )
        )
        contract_id, outcome_due_date = cur.fetchone()

        cur.execute(
            """
            UPDATE decision_intelligence.project_decision_contract_draft_v291
            SET status='ACTIVE'
            WHERE draft_id=%s
            """,
            (draft["draft_id"],)
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_event_v292(
                contract_id, draft_id, project_key, event_type, actor, payload
            )
            VALUES(%s,%s,%s,'CONTRACT_ACTIVATED',%s,%s::jsonb)
            """,
            (
                contract_id,
                draft["draft_id"],
                project_key,
                activated_by,
                json.dumps(
                    {
                        "contract_code": contract_code,
                        "outcome_due_date": outcome_due_date,
                        "baseline_hash": approval["baseline_hash"],
                    },
                    ensure_ascii=False,
                    default=jd,
                ),
            )
        )

    conn.commit()
    print(
        f"[V2.9.2] {project_key} ACTIVE | "
        f"contract={contract_code} | outcome_due={outcome_due_date}"
    )


def open_contract(cur, project_key: str):
    return fetch_one(
        cur,
        """
        SELECT *
        FROM decision_intelligence.project_active_contract_v292
        WHERE project_key=%s
          AND status IN ('ACTIVE','WAITING_OUTCOME','OUTCOME_MATURE')
        ORDER BY activated_at DESC, contract_id DESC
        LIMIT 1
        """,
        (project_key,)
    )


def record_outcome(
    conn,
    project_key: str,
    metric_value: float,
    recorded_by: str,
    observed_at: str | None = None,
    value_realized: float | None = None,
    source_reference: str | None = None,
    evidence_note: str | None = None,
):
    with conn.cursor() as cur:
        contract = open_contract(cur, project_key)
        if not contract:
            raise ValueError(f"{project_key}: no existe contrato activo.")

        obs = (
            datetime.fromisoformat(observed_at)
            if observed_at
            else datetime.now(timezone.utc)
        )
        if obs.tzinfo is None:
            obs = obs.replace(tzinfo=timezone.utc)

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_outcome_v292(
                contract_id, project_key,
                observed_at, metric_name, metric_value,
                value_realized, currency,
                source_reference, evidence_note, recorded_by
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING outcome_id
            """,
            (
                contract["contract_id"],
                project_key,
                obs,
                contract["primary_metric"],
                metric_value,
                value_realized,
                contract.get("currency") or "PEN",
                source_reference,
                evidence_note,
                recorded_by,
            )
        )
        outcome_id = cur.fetchone()[0]

        mature = obs.date() >= contract["outcome_due_date"]
        new_status = "OUTCOME_MATURE" if mature else "WAITING_OUTCOME"

        cur.execute(
            """
            UPDATE decision_intelligence.project_active_contract_v292
            SET status=%s
            WHERE contract_id=%s
            """,
            (new_status, contract["contract_id"])
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_event_v292(
                contract_id, draft_id, project_key, event_type, actor, payload
            )
            VALUES(%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                contract["contract_id"],
                contract["draft_id"],
                project_key,
                "MATURE_OUTCOME_RECORDED" if mature else "INTERIM_OUTCOME_RECORDED",
                recorded_by,
                json.dumps(
                    {
                        "outcome_id": outcome_id,
                        "metric_value": metric_value,
                        "value_realized": value_realized,
                        "observed_at": obs,
                    },
                    ensure_ascii=False,
                    default=jd,
                ),
            )
        )

    conn.commit()
    print(
        f"[V2.9.2] {project_key} outcome recorded | "
        f"outcome_id={outcome_id} | status={new_status}"
    )


def complete_learning(conn, project_key: str, completed_by: str, summary: str):
    with conn.cursor() as cur:
        contract = open_contract(cur, project_key)
        if not contract:
            # also allow contract already marked OUTCOME_MATURE but open_contract includes it
            raise ValueError(f"{project_key}: no existe contrato elegible.")

        cur.execute(
            """
            SELECT count(*)
            FROM decision_intelligence.project_contract_outcome_v292
            WHERE contract_id=%s
              AND observed_at::date >= %s
            """,
            (contract["contract_id"], contract["outcome_due_date"])
        )
        mature_count = int(cur.fetchone()[0])

        if mature_count < 1:
            raise ValueError(
                f"{project_key}: no existe outcome maduro; no se puede completar aprendizaje."
            )

        cur.execute(
            """
            UPDATE decision_intelligence.project_active_contract_v292
            SET
                status='LEARNING_COMPLETE',
                learning_completed_at=now(),
                learning_completed_by=%s,
                learning_summary=%s
            WHERE contract_id=%s
            """,
            (completed_by, summary, contract["contract_id"])
        )

        cur.execute(
            """
            UPDATE decision_intelligence.project_decision_contract_draft_v291
            SET status='LEARNING_COMPLETE'
            WHERE draft_id=%s
            """,
            (contract["draft_id"],)
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_event_v292(
                contract_id, draft_id, project_key, event_type, actor, payload
            )
            VALUES(%s,%s,%s,'LEARNING_COMPLETE',%s,%s::jsonb)
            """,
            (
                contract["contract_id"],
                contract["draft_id"],
                project_key,
                completed_by,
                json.dumps({"learning_summary": summary}, ensure_ascii=False),
            )
        )

    conn.commit()
    print(f"[V2.9.2] {project_key} LEARNING_COMPLETE")


def cancel(conn, project_key: str, cancelled_by: str, reason: str):
    with conn.cursor() as cur:
        contract = open_contract(cur, project_key)
        if not contract:
            raise ValueError(f"{project_key}: no existe contrato abierto.")

        cur.execute(
            """
            UPDATE decision_intelligence.project_active_contract_v292
            SET
                status='CANCELLED',
                cancelled_at=now(),
                cancelled_by=%s,
                cancel_reason=%s
            WHERE contract_id=%s
            """,
            (cancelled_by, reason, contract["contract_id"])
        )

        cur.execute(
            """
            UPDATE decision_intelligence.project_decision_contract_draft_v291
            SET status='CANCELLED'
            WHERE draft_id=%s
            """,
            (contract["draft_id"],)
        )

        cur.execute(
            """
            INSERT INTO decision_intelligence.project_contract_event_v292(
                contract_id, draft_id, project_key, event_type, actor, payload
            )
            VALUES(%s,%s,%s,'CONTRACT_CANCELLED',%s,%s::jsonb)
            """,
            (
                contract["contract_id"],
                contract["draft_id"],
                project_key,
                cancelled_by,
                json.dumps({"reason": reason}, ensure_ascii=False),
            )
        )
    conn.commit()
    print(f"[V2.9.2] {project_key} CANCELLED")


def export_artifacts(root: Path, conn):
    out = root / "artifacts" / "contract_activation_v292"
    out.mkdir(parents=True, exist_ok=True)

    with conn.cursor() as cur:
        board = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_contract_command_center_v292
            ORDER BY
                CASE route_status
                    WHEN 'ACTIVATION_CANDIDATE' THEN 1
                    WHEN 'DESIGN_ONLY' THEN 2
                    WHEN 'BLOCKED_RECONCILIATION' THEN 3
                    WHEN 'EVIDENCE_BUILDING' THEN 4
                    ELSE 9
                END,
                priority_score DESC NULLS LAST,
                project_key
            """
        )
        sla = fetch_dicts(
            cur,
            """
            SELECT *
            FROM decision_intelligence.v_outcome_sla_v292
            """
        )

    def write_csv(name, rows):
        p = out / name
        if not rows:
            p.write_text("", encoding="utf-8")
            return
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    write_csv("contract_command_center.csv", board)
    write_csv("outcome_sla.csv", sla)

    lines = [
        "# Medallio v2.9.2 — Human Approval / Activation / Outcome SLA",
        "",
        "| Project | Route | Eligible | Workflow | Owner | Deadline | SLA | Outcome due |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in board:
        lines.append(
            f"| {r.get('project_key')} | {r.get('route_status')} | "
            f"{r.get('activation_eligible')} | {r.get('workflow_status')} | "
            f"{r.get('owner_confirmed') or ''} | {r.get('approved_deadline') or ''} | "
            f"{r.get('sla_status') or ''} | {r.get('outcome_due_date') or ''} |"
        )

    lines += [
        "",
        "## Operating rule",
        "",
        "- MD / MT: activation candidates, but human approval is mandatory.",
        "- CP: DESIGN_ONLY.",
        "- NP: BLOCKED_RECONCILIATION.",
        "- SL: EVIDENCE_BUILDING.",
        "- No project is activated by installation or AI recommendation alone.",
        "",
    ]
    (out / "contract_command_center.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    # Optional simple chart for executive review.
    try:
        import matplotlib.pyplot as plt

        labels = [r["project_key"] for r in board]
        route_rank = {
            "ACTIVATION_CANDIDATE": 4,
            "DESIGN_ONLY": 3,
            "BLOCKED_RECONCILIATION": 2,
            "EVIDENCE_BUILDING": 1,
        }
        vals = [route_rank.get(r["route_status"], 0) for r in board]

        fig, ax = plt.subplots(figsize=(10, 5.5))
        ax.barh(labels[::-1], vals[::-1])
        ax.set_title("Medallio v2.9.2 — ruta operativa del portfolio priorizado")
        ax.set_xlabel("Ruta (1=evidencia, 2=reconciliar, 3=diseñar, 4=candidato activación)")
        ax.set_xlim(0, 4.5)
        fig.tight_layout()
        fig.savefig(out / "11_contract_activation_routes.png", dpi=160)
        plt.close(fig)
    except Exception:
        pass


def status(root: Path, conn):
    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_contract_command_center_v292
            ORDER BY
                CASE route_status
                    WHEN 'ACTIVATION_CANDIDATE' THEN 1
                    WHEN 'DESIGN_ONLY' THEN 2
                    WHEN 'BLOCKED_RECONCILIATION' THEN 3
                    WHEN 'EVIDENCE_BUILDING' THEN 4
                    ELSE 9
                END,
                priority_score DESC NULLS LAST,
                project_key
            """
        )

    print(f"[V2.9.2] portfolio routes={len(rows)}")
    for r in rows:
        print(
            f"  {r['project_key']} | route={r['route_status']} | "
            f"workflow={r.get('workflow_status')} | "
            f"eligible={r['activation_eligible']} | "
            f"contract={r.get('contract_code')} | "
            f"sla={r.get('sla_status')}"
        )

    export_artifacts(root, conn)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        nargs="?",
        choices=[
            "install", "refresh", "status", "approve", "activate",
            "record-outcome", "complete-learning", "cancel"
        ],
        default="status",
    )
    p.add_argument("--file")
    p.add_argument("--project")
    p.add_argument("--actor")
    p.add_argument("--metric-value", type=float)
    p.add_argument("--value-realized", type=float)
    p.add_argument("--observed-at")
    p.add_argument("--source-reference")
    p.add_argument("--evidence-note")
    p.add_argument("--summary")
    p.add_argument("--reason")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install_schema(root, conn)
            sync_routes(root, conn)
            write_approval_templates(root, conn)
            export_artifacts(root, conn)
            print("[V2.9.2] schema/routes/templates: OK")
            status(root, conn)
            return

        if args.command == "refresh":
            sync_routes(root, conn)
            write_approval_templates(root, conn)
            export_artifacts(root, conn)
            print("[V2.9.2] refreshed.")
            status(root, conn)
            return

        if args.command == "approve":
            if not args.file:
                raise SystemExit("--file es obligatorio.")
            approve(root, conn, args.file)
            export_artifacts(root, conn)
            return

        if args.command == "activate":
            if not args.project or not args.actor:
                raise SystemExit("--project y --actor son obligatorios.")
            activate(conn, args.project, args.actor)
            export_artifacts(root, conn)
            return

        if args.command == "record-outcome":
            if args.project is None or args.actor is None or args.metric_value is None:
                raise SystemExit(
                    "--project, --actor y --metric-value son obligatorios."
                )
            record_outcome(
                conn,
                args.project,
                args.metric_value,
                args.actor,
                observed_at=args.observed_at,
                value_realized=args.value_realized,
                source_reference=args.source_reference,
                evidence_note=args.evidence_note,
            )
            export_artifacts(root, conn)
            return

        if args.command == "complete-learning":
            if not args.project or not args.actor or not args.summary:
                raise SystemExit(
                    "--project, --actor y --summary son obligatorios."
                )
            complete_learning(conn, args.project, args.actor, args.summary)
            export_artifacts(root, conn)
            return

        if args.command == "cancel":
            if not args.project or not args.actor or not args.reason:
                raise SystemExit(
                    "--project, --actor y --reason son obligatorios."
                )
            cancel(conn, args.project, args.actor, args.reason)
            export_artifacts(root, conn)
            return

        status(root, conn)


if __name__ == "__main__":
    main()
