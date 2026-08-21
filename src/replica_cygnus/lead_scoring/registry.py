from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LeadScoringConfig
from .metrics import binary_metrics, priority_metrics, promotion_gate
from .training import load_artifact, load_evaluation_frame

DECISION_SYSTEM = "priorizacion_leads"
MODEL_NAME = "lead_priority_bundle"


def _get_run(conn, model_run_id: str) -> dict[str, Any]:
    with conn.cursor() as cursor:
        cursor.execute("""SELECT model_run_id::text,decision_system,model_name,model_version,trained_at,
                          metrics,parameters,artifact_uri,status
                          FROM model_control.model_runs WHERE model_run_id=%s::uuid""",(model_run_id,))
        row=cursor.fetchone()
    if not row:
        raise RuntimeError(f"No existe model_run_id={model_run_id}")
    return {"model_run_id":row[0],"decision_system":row[1],"model_name":row[2],"model_version":row[3],
            "trained_at":row[4],"metrics":row[5] if isinstance(row[5],dict) else json.loads(row[5] or "{}"),
            "parameters":row[6] if isinstance(row[6],dict) else json.loads(row[6] or "{}"),
            "artifact_uri":row[7],"status":row[8]}


def _get_alias(conn, alias_name: str) -> dict[str, Any] | None:
    with conn.cursor() as cursor:
        cursor.execute("""SELECT a.model_run_id::text,mr.model_version,mr.artifact_uri,mr.status,a.updated_at
          FROM model_control.model_aliases a JOIN model_control.model_runs mr ON mr.model_run_id=a.model_run_id
          WHERE a.decision_system=%s AND a.model_name=%s AND a.alias_name=%s""",
          (DECISION_SYSTEM,MODEL_NAME,alias_name))
        row=cursor.fetchone()
    if not row:
        return None
    return {"model_run_id":row[0],"model_version":row[1],"artifact_uri":row[2],"status":row[3],"updated_at":row[4]}


def _bundle_metrics(artifact: dict[str,Any], frame, cfg: LeadScoringConfig, metric_type: str) -> dict[str,Any]:
    p_sep=artifact["sep_model"].predict_probability(frame)
    p_minuta=artifact["minuta_model"].predict_probability(frame)
    return {"type":metric_type,
      "sep":binary_metrics(frame["separacion_14d"],p_sep,cfg.promotion.top_fraction),
      "minuta":binary_metrics(frame["minuta_60d"],p_minuta,cfg.promotion.top_fraction),
      "priority":priority_metrics(frame["separacion_14d"],frame["minuta_60d"],p_sep,p_minuta,
                                  artifact["weight_sep"],artifact["weight_minuta"],cfg.promotion.top_fraction)}


def evaluate_challenger(conn, cfg: LeadScoringConfig, project_root: Path, model_run_id: str) -> dict[str,Any]:
    candidate_run=_get_run(conn,model_run_id)
    if candidate_run["status"] not in {"CHALLENGER","PROVISIONAL"}:
        raise RuntimeError(f"El run no es challenger/provisional: {candidate_run['status']}")
    artifact=load_artifact(project_root,candidate_run["artifact_uri"])
    test_window=candidate_run["metrics"].get("common_test") or {}
    if not test_window.get("from") or not test_window.get("to"):
        raise RuntimeError("El challenger no registró ventana common_test.")
    evaluation=load_evaluation_frame(conn,test_window["from"],test_window["to"])
    if evaluation.empty:
        raise RuntimeError("No se pudo reconstruir el test común del challenger.")
    candidate=_bundle_metrics(artifact,evaluation,cfg,"CHALLENGER")
    serving=_get_alias(conn,"serving")
    comparator_run_id=None
    if serving and serving["model_run_id"] != model_run_id:
        comparator=_bundle_metrics(load_artifact(project_root,serving["artifact_uri"]),evaluation,cfg,"SERVING_INCUMBENT")
        comparator_run_id=serving["model_run_id"]
    else:
        comparator=candidate_run["metrics"]["baseline"]
    passed,reasons,details=promotion_gate(candidate,comparator,cfg.promotion)
    promotion_id=str(uuid.uuid4())
    decision="PASS_FOR_REVIEW" if passed else "REJECT"
    bootstrap=passed and serving is None
    if bootstrap:
        decision="PROVISIONAL_SERVING"
    with conn.cursor() as cursor:
        cursor.execute("""INSERT INTO model_control.model_promotions
          (promotion_id,decision_system,model_name,candidate_model_run_id,incumbent_model_run_id,evaluated_at,
           gate_status,decision,gate_details,reasons,approved_at,approved_by)
          VALUES (%s::uuid,%s,%s,%s::uuid,%s::uuid,%s,%s,%s,%s::jsonb,%s::jsonb,NULL,NULL)""",
          (promotion_id,DECISION_SYSTEM,MODEL_NAME,model_run_id,comparator_run_id,datetime.now(timezone.utc),
           "PASS" if passed else "FAIL",decision,json.dumps(details),json.dumps(reasons,ensure_ascii=False)))
        if bootstrap:
            cursor.execute("""INSERT INTO model_control.model_aliases
              (decision_system,model_name,alias_name,model_run_id,updated_at) VALUES (%s,%s,'serving',%s::uuid,now())
              ON CONFLICT (decision_system,model_name,alias_name) DO UPDATE SET model_run_id=EXCLUDED.model_run_id,updated_at=now()""",
              (DECISION_SYSTEM,MODEL_NAME,model_run_id))
            cursor.execute("UPDATE model_control.model_runs SET status='PROVISIONAL' WHERE model_run_id=%s::uuid",(model_run_id,))
    conn.commit()
    return {"promotion_id":promotion_id,"candidate_model_run_id":model_run_id,"comparator_model_run_id":comparator_run_id,
            "passed":passed,"decision":decision,"reasons":reasons,"details":details}


def approve_promotion(conn, model_run_id: str, approved_by: str) -> dict[str,Any]:
    if not approved_by.strip():
        raise ValueError("approved_by es obligatorio para una promoción a CHAMPION.")
    run=_get_run(conn,model_run_id)
    with conn.cursor() as cursor:
        cursor.execute("""SELECT promotion_id::text,gate_status,decision FROM model_control.model_promotions
                          WHERE candidate_model_run_id=%s::uuid ORDER BY evaluated_at DESC LIMIT 1""",(model_run_id,))
        row=cursor.fetchone()
        if not row:
            raise RuntimeError("El challenger todavía no tiene evaluación de promoción.")
        promotion_id,gate_status,decision=row
        if gate_status != "PASS":
            raise RuntimeError(f"No se puede promover: gate_status={gate_status}, decision={decision}")
        incumbent=_get_alias(conn,"champion")
        if incumbent and incumbent["model_run_id"] != model_run_id:
            cursor.execute("UPDATE model_control.model_runs SET status='ARCHIVED' WHERE model_run_id=%s::uuid AND status='CHAMPION'",
                           (incumbent["model_run_id"],))
        for alias_name in ("champion","serving"):
            cursor.execute("""INSERT INTO model_control.model_aliases
             (decision_system,model_name,alias_name,model_run_id,updated_at) VALUES (%s,%s,%s,%s::uuid,now())
             ON CONFLICT (decision_system,model_name,alias_name) DO UPDATE SET model_run_id=EXCLUDED.model_run_id,updated_at=now()""",
             (DECISION_SYSTEM,MODEL_NAME,alias_name,model_run_id))
        cursor.execute("UPDATE model_control.model_runs SET status='CHAMPION' WHERE model_run_id=%s::uuid",(model_run_id,))
        cursor.execute("UPDATE model_control.model_promotions SET decision='PROMOTED',approved_at=now(),approved_by=%s WHERE promotion_id=%s::uuid",
                       (approved_by,promotion_id))
    conn.commit()
    return {"model_run_id":model_run_id,"model_version":run["model_version"],"status":"CHAMPION","approved_by":approved_by}


def serving_model(conn) -> dict[str,Any]:
    serving=_get_alias(conn,"serving")
    if serving is None:
        raise RuntimeError("No existe alias serving. Entrena/evalúa un challenger y supera el gate primero.")
    return serving


def model_status(conn) -> list[tuple]:
    with conn.cursor() as cursor:
        cursor.execute("""SELECT mr.model_run_id::text,mr.model_version,mr.trained_at,mr.status,
          COALESCE(string_agg(a.alias_name,',' ORDER BY a.alias_name),'') AS aliases
          FROM model_control.model_runs mr LEFT JOIN model_control.model_aliases a ON a.model_run_id=mr.model_run_id
           AND a.decision_system=mr.decision_system AND a.model_name=mr.model_name
          WHERE mr.decision_system=%s AND mr.model_name=%s
          GROUP BY mr.model_run_id,mr.model_version,mr.trained_at,mr.status ORDER BY mr.trained_at DESC LIMIT 20""",
          (DECISION_SYSTEM,MODEL_NAME))
        return cursor.fetchall()
