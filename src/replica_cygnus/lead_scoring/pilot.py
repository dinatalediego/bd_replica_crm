"""Prospective pilot. Every mutation is explicit; this module never contacts leads."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

UTC = timezone.utc
HORIZONS = {"separacion_14d": 14, "minuta_60d": 60}
ACTIONS = {"CALL", "WHATSAPP", "VISIT_SCHEDULED", "VISIT_COMPLETED", "NO_CONTACT"}


def timestamp(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp requiere zona horaria, por ejemplo -05:00")
    return result.astimezone(UTC)


def required(value, name):
    if value is None or not str(value).strip():
        raise ValueError(f"Falta {name}")
    return str(value).strip()


def validate_protocol(p):
    required(p.get("pilot_id"), "pilot_id")
    UUID(required(p.get("model_run_id"), "model_run_id"))
    if len(required(p.get("seed"), "seed")) < 16:
        raise ValueError("seed necesita al menos 16 caracteres aleatorios; congelar antes de reclutar")
    if not isinstance(p.get("projects"), list) or not p["projects"] or any(not str(x).strip() for x in p["projects"]):
        raise ValueError("projects debe contener códigos aprobados")
    for key, low, high in (("min_priority_score", 0, 100), ("treatment_fraction", .1, .9),
                           ("max_age_hours", .01, 336), ("max_score_age_hours", .01, 24),
                           ("sla_minutes", 1, 1440), ("target_per_arm", 1, 1000000)):
        v = p.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{key} fuera de rango o pendiente")
    if int(p["sla_minutes"]) != p["sla_minutes"] or int(p["target_per_arm"]) != p["target_per_arm"]:
        raise ValueError("sla_minutes y target_per_arm deben ser enteros")
    if p.get("primary_outcome") not in HORIZONS:
        raise ValueError("primary_outcome inválido")
    timestamp(p.get("enrollment_end"))
    for key in ("treatment_description", "control_description", "eligibility_definition", "outcome_definition", "analysis_plan"):
        text = required(p.get(key), key)
        if "PENDIENTE" in text.upper():
            raise ValueError(f"Aprobar {key} antes de registrar el protocolo")
    if p.get("business_rules_approved") is not True:
        raise ValueError("Falta aprobación de reglas comerciales")
    return p


def subject_key(document):
    # Preserve leading zeros and punctuation: normalization must be upstream and approved.
    return hashlib.sha256(required(document, "documento_cliente").strip().encode()).hexdigest()


def assigned_arm(p, subject):
    digest = hashlib.sha256(f"{p['pilot_id']}|{p['seed']}|{subject}".encode()).digest()
    return "TREATMENT" if int.from_bytes(digest, "big") / 2**256 < p["treatment_fraction"] else "CONTROL"


def _audit(cur, pilot_id, operator, event, details):
    cur.execute("INSERT INTO experiments.lead_pilot_audit(pilot_id,operator,event_type,details) VALUES (%s,%s,%s,%s)",
                (pilot_id, required(operator, "operator"), event, Jsonb(details)))


def create_pilot(conn, protocol, operator):
    p = validate_protocol(protocol)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT protocol FROM experiments.lead_pilots WHERE pilot_id=%s", (p["pilot_id"],))
        old = cur.fetchone()
        if old:
            if old["protocol"] != p:
                raise ValueError("Protocolo inmutable: crear otro pilot_id para cambiarlo")
            return "EXISTING"
        cur.execute("SELECT 1 FROM model_control.model_runs WHERE model_run_id=%s", (p["model_run_id"],))
        if not cur.fetchone():
            raise ValueError("Modelo no registrado")
        cur.execute("INSERT INTO experiments.lead_pilots(pilot_id,protocol) VALUES (%s,%s)", (p["pilot_id"], Jsonb(p)))
        _audit(cur, p["pilot_id"], operator, "CREATE_DRAFT", {})
    return "CREATED_DRAFT"


def set_status(conn, pilot_id, status, operator):
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM experiments.lead_pilots WHERE pilot_id=%s FOR UPDATE", (pilot_id,))
        p = cur.fetchone()
        if not p:
            raise ValueError("Piloto inexistente")
        allowed = {"DRAFT": {"ACTIVE", "CLOSED"}, "ACTIVE": {"PAUSED", "CLOSED"}, "PAUSED": {"ACTIVE", "CLOSED"}, "CLOSED": set()}
        if status not in allowed[p["status"]]:
            raise ValueError("Transición no permitida")
        if status == "ACTIVE":
            validate_protocol(p["protocol"])
            if timestamp(p["protocol"]["enrollment_end"]) <= datetime.now(UTC):
                raise ValueError("Ventana de reclutamiento vencida")
            cur.execute("SELECT 1 FROM model_control.model_aliases WHERE model_run_id=%s AND alias_name='serving'", (p["protocol"]["model_run_id"],))
            if not cur.fetchone():
                raise ValueError("El modelo congelado no tiene alias serving")
        cur.execute("""UPDATE experiments.lead_pilots SET status=%s,updated_at=now(),approved_by=%s,
                    activated_at=CASE WHEN %s='ACTIVE' THEN coalesce(activated_at,now()) ELSE activated_at END
                    WHERE pilot_id=%s""", (status, required(operator, "operator"), status, pilot_id))
        _audit(cur, pilot_id, operator, status, {"previous": p["status"]})


def _record_batch(cur, pilot_id, kind, source, accepted, existing, rejects):
    batch = uuid4()
    cur.execute("""INSERT INTO experiments.lead_pilot_batches
      (batch_id,pilot_id,batch_type,source_rows,accepted_rows,existing_rows,rejected_rows)
      VALUES (%s,%s,%s,%s,%s,%s,%s)""", (batch,pilot_id,kind,source,accepted,existing,len(rejects)))
    for index, key, reason in rejects:
        cur.execute("INSERT INTO experiments.lead_pilot_rejects VALUES (%s,%s,%s,%s)", (batch,index,key,reason))
    return {"batch_id":str(batch),"source_rows":source,"accepted_rows":accepted,"existing_rows":existing,
            "rejected_rows":len(rejects),"reconciled":source==accepted+existing+len(rejects),"rejects":rejects}


def enroll(conn, pilot_id, operator, eligibility, apply=False):
    """eligibility maps evidence_key to reviewed CRM reference. Preview writes nothing.

    Approval roster is intentional: scores do not prove consent or absence of prior deals.
    """
    operator = required(operator, "operator")
    if any(not isinstance(k,str) or not k.strip() for k in eligibility):
        raise ValueError("CSV de elegibilidad contiene evidence_key vacío")
    source_indices = {key:i for i,key in enumerate(eligibility,2)}
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM experiments.lead_pilots WHERE pilot_id=%s FOR UPDATE", (pilot_id,))
        pilot = cur.fetchone()
        if not pilot or pilot["status"] != "ACTIVE":
            raise ValueError("El piloto debe estar ACTIVE")
        p = pilot["protocol"]
        now = datetime.now(UTC)
        if now >= timestamp(p["enrollment_end"]):
            raise ValueError("Reclutamiento cerrado por fecha")
        cur.execute("""SELECT s.*,e.documento_cliente,e.codigo_proyecto,e.asesor,e.canal,e.evidence_source
             FROM decision_intelligence.lead_scores s JOIN features.lead_evidence e USING(evidence_key)
             WHERE s.model_run_id=%s AND s.evidence_key=ANY(%s)
             ORDER BY s.decision_at,s.evidence_key""", (p["model_run_id"], list(eligibility)))
        candidates = {r["evidence_key"]:r for r in cur.fetchall()}
        cur.execute("""SELECT a.subject_key,a.pilot_id FROM experiments.lead_pilot_assignments a
             WHERE a.pilot_id=%s OR a.assigned_at+interval '60 days'>%s""", (pilot_id, now))
        occupied = {r["subject_key"]:r["pilot_id"] for r in cur.fetchall()}
        cur.execute("SELECT arm,count(*) AS n FROM experiments.lead_pilot_assignments WHERE pilot_id=%s GROUP BY arm", (pilot_id,))
        counts = {r["arm"]:r["n"] for r in cur.fetchall()}
        rejects, accepted, existing, preview = [], 0, 0, []
        # Stable order independent of CSV sorting.
        for index, key in enumerate(sorted(eligibility, key=lambda k: (candidates[k]["decision_at"], k) if k in candidates else (datetime.max.replace(tzinfo=UTC),k)), 1):
            try:
                ref = required(eligibility[key], "eligibility source_ref")
                r = candidates.get(key)
                if not r:
                    raise ValueError("NO_SCORE_FOR_FROZEN_MODEL")
                subject = subject_key(r["documento_cliente"])
                if subject in occupied:
                    if occupied[subject] == pilot_id:
                        existing += 1
                        continue
                    raise ValueError("OTHER_PILOT_FOLLOWUP")
                if min(counts.get("TREATMENT",0), counts.get("CONTROL",0)) >= p["target_per_arm"]:
                    raise ValueError("TARGET_REACHED")
                if r["evidence_source"] != "LIVE":
                    raise ValueError("NOT_LIVE")
                if not pilot["activated_at"] <= r["decision_at"] <= r["scored_at"] <= now:
                    raise ValueError("NOT_PROSPECTIVE_OR_INVALID_TIME")
                if r["decision_at"] < now-timedelta(hours=p["max_age_hours"]) or r["scored_at"] < now-timedelta(hours=p["max_score_age_hours"]):
                    raise ValueError("STALE_EVIDENCE_OR_SCORE")
                if r["codigo_proyecto"] not in p["projects"] or r["priority_score"] < p["min_priority_score"]:
                    raise ValueError("OUTSIDE_APPROVED_SCOPE")
                arm = assigned_arm(p,subject)
                aid = uuid4()
                if apply:
                    cur.execute("""INSERT INTO experiments.lead_pilot_assignments
                    (assignment_id,pilot_id,subject_key,evidence_key,score_id,model_run_id,arm,assigned_at,
                    decision_at,scored_at,codigo_proyecto,asesor,canal,priority_score,p_separacion_14d,p_minuta_60d)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (aid,pilot_id,subject,key,r["score_id"],r["model_run_id"],arm,now,r["decision_at"],r["scored_at"],
                     r["codigo_proyecto"],r["asesor"],r["canal"],r["priority_score"],r["p_separacion_14d"],r["p_minuta_60d"]))
                    _audit(cur,pilot_id,operator,"ENROLL",{"assignment_id":str(aid),"source_ref":ref})
                preview.append({"evidence_key":key,"arm":arm if apply else "HIDDEN_UNTIL_APPLY",
                                "assignment_id":str(aid) if apply else None})
                occupied[subject]=pilot_id
                counts[arm]=counts.get(arm,0)+1
                accepted += 1
            except ValueError as exc:
                rejects.append((source_indices[key],key,str(exc)))
        if apply:
            result = _record_batch(cur,pilot_id,"ENROLL",len(eligibility),accepted,existing,rejects)
        else:
            result = {"dry_run":True,"source_rows":len(eligibility),"accepted_rows":accepted,"existing_rows":existing,"rejected_rows":len(rejects),"rejects":rejects}
        result["assignments"] = preview
        return result


def validate_event(row, assigned_at, now, kind):
    aid = str(UUID(required(row.get("assignment_id"),"assignment_id")))
    source = required(row.get("source_ref"), "source_ref")
    if kind == "actions":
        when = timestamp(row.get("action_at"))
        if not assigned_at <= when <= now:
            raise ValueError("ACTION_OUTSIDE_ASSIGNMENT_TIME")
        action = row.get("action_type")
        if action not in ACTIONS:
            raise ValueError("INVALID_ACTION_TYPE")
        try:
            cost = Decimal(str(row.get("cost_pen")))
        except InvalidOperation as exc:
            raise ValueError("INVALID_COST") from exc
        if not cost.is_finite() or cost < 0 or cost >= Decimal("100000000000000") or cost != cost.quantize(Decimal('.0001')):
            raise ValueError("INVALID_COST")
        return dict(event_id=str(UUID(required(row.get("event_id"),"event_id"))),assignment_id=aid,
                    action_at=when,action_type=action,result=required(row.get("result"),"result"),
                    owner=required(row.get("owner"),"owner"),cost_pen=cost,source_ref=source)
    name = row.get("outcome_name")
    if name not in HORIZONS or str(row.get("value")) not in {"0","1"}:
        raise ValueError("INVALID_OUTCOME")
    end = assigned_at+timedelta(days=HORIZONS[name])
    through = timestamp(row.get("observed_through"))
    if not end <= through <= now:
        raise ValueError("HORIZON_NOT_FULLY_OBSERVED")
    value = int(row["value"])
    event = timestamp(row["event_at"]) if row.get("event_at") else None
    if (value==1 and (event is None or not assigned_at <= event < end)) or (value==0 and event is not None):
        raise ValueError("EVENT_OUTSIDE_HORIZON_OR_INCONSISTENT")
    return dict(assignment_id=aid,outcome_name=name,value=value,event_at=event,observed_through=through,
                source_ref=source,verified_by=required(row.get("verified_by"),"verified_by"))


def import_events(conn, pilot_id, rows, kind, operator):
    if kind not in {"actions","outcomes"}:
        raise ValueError("kind inválido")
    from psycopg import sql
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT 1 FROM experiments.lead_pilots WHERE pilot_id=%s FOR UPDATE", (pilot_id,))
        if not cur.fetchone():
            raise ValueError("Piloto inexistente")
        accepted, existing, rejects = 0, 0, []
        for index, row in enumerate(rows, 2):
            try:
                aid = str(UUID(required(row.get("assignment_id"),"assignment_id")))
                cur.execute("SELECT assigned_at FROM experiments.lead_pilot_assignments WHERE pilot_id=%s AND assignment_id=%s", (pilot_id,aid))
                assignment = cur.fetchone()
                if not assignment:
                    raise ValueError("UNKNOWN_ASSIGNMENT_IN_PILOT")
                data = validate_event(row,assignment["assigned_at"],datetime.now(UTC),kind)
                table = sql.Identifier("experiments", "lead_pilot_"+kind)
                keys = ["event_id"] if kind=="actions" else ["assignment_id","outcome_name"]
                predicate = sql.SQL(" AND ").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in keys)
                cur.execute(sql.SQL("SELECT * FROM {} WHERE {}").format(table,predicate),[data[k] for k in keys])
                old = cur.fetchone()
                if old:
                    # Compare instants and decimals by value; DB timezone rendering may differ.
                    if any((str(old[k]) != str(v) if isinstance(old[k], UUID) else old[k] != v)
                           for k,v in data.items()):
                        raise ValueError("CONFLICTING_RETRY_REQUIRES_REVIEW")
                    existing += 1
                    continue
                cur.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(table,
                    sql.SQL(',').join(map(sql.Identifier,data)),sql.SQL(',').join(sql.Placeholder() for _ in data)), list(data.values()))
                accepted += 1
            except (ValueError, TypeError) as exc:
                rejects.append((index,str(row.get("assignment_id", "")),str(exc)))
        result = _record_batch(cur,pilot_id,kind.upper(),len(rows),accepted,existing,rejects)
        _audit(cur,pilot_id,operator,"IMPORT_"+kind.upper(),{"batch_id":result["batch_id"]})
        return result


def itt_comparison(t_positive, t_n, c_positive, c_n):
    """Use only mature complete cohorts; missing outcomes must be checked by caller."""
    from statsmodels.stats.proportion import confint_proportions_2indep
    if min(t_n,c_n) <= 0:
        return {"status":"INSUFFICIENT_MATURE_DATA"}
    if not (0<=t_positive<=t_n and 0<=c_positive<=c_n):
        raise ValueError("Conteos inválidos")
    lo,hi=confint_proportions_2indep(t_positive,t_n,c_positive,c_n,method="newcomb",compare="diff")
    diff=t_positive/t_n-c_positive/c_n
    return {"status":"DESCRIPTIVE_NOT_STOPPING_RULE","difference_pp":100*diff,
            "ci95_low_pp":100*float(lo),"ci95_high_pp":100*float(hi),
            "relative_lift":None if c_positive==0 else (t_positive/t_n)/(c_positive/c_n)-1}
