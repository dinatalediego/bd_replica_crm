from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .config import LeadScoringConfig


DECISION_SYSTEM = "priorizacion_leads"
RECOMMENDATION_NAMESPACE = uuid.UUID("c5a22a14-0b12-4c8c-8bd2-e0b09c935849")
OUTCOME_NAMESPACE = uuid.UUID("4c10454f-cc89-42ce-9e8d-16ff439c465f")


def recommended_action_for_band(priority_band: str) -> str:
    """Traduce prioridad predictiva a una acción operativa, no causal."""
    actions = {
        "A": "CONTACTAR_PRIORIDAD_ALTA",
        "B": "CONTACTAR",
        "C": "NURTURE",
        "D": "NURTURE",
    }
    try:
        return actions[priority_band]
    except KeyError as exc:
        raise ValueError(f"Banda de prioridad no soportada: {priority_band}") from exc


def recommendation_id_for_score(score_id: str) -> str:
    return str(uuid.uuid5(RECOMMENDATION_NAMESPACE, f"lead-score:{score_id}"))


def outcome_id_for_evidence(evidence_key: str, outcome_name: str) -> str:
    return str(uuid.uuid5(OUTCOME_NAMESPACE, f"{evidence_key}:{outcome_name}"))


def sync_recommendations(conn) -> int:
    """Materializa scores del modelo serving como recomendaciones idempotentes."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (s.evidence_key)
              s.score_id::text,s.evidence_key,s.lead_id,s.scored_at,s.model_run_id::text,
              s.p_separacion_14d,s.p_minuta_60d,s.priority_score,s.priority_rank,s.priority_band,
              e.codigo_proyecto,e.asesor,e.canal,e.medio
            FROM decision_intelligence.lead_scores s
            JOIN features.lead_evidence e USING (evidence_key)
            JOIN model_control.model_runs mr ON mr.model_run_id=s.model_run_id
            JOIN model_control.model_aliases a ON a.model_run_id=s.model_run_id
              AND a.decision_system=mr.decision_system
              AND a.model_name=mr.model_name
              AND a.alias_name='serving'
            ORDER BY s.evidence_key,s.scored_at DESC
            """
        )
        rows = cursor.fetchall()

    records = []
    for row in rows:
        (
            score_id,
            evidence_key,
            lead_id,
            scored_at,
            model_run_id,
            p_sep,
            p_minuta,
            priority_score,
            priority_rank,
            priority_band,
            project,
            advisor,
            channel,
            medium,
        ) = row
        context = {
            "semantics": "PROPENSITY_NOT_CAUSAL_UPLIFT",
            "score_id": score_id,
            "evidence_key": evidence_key,
            "lead_id": lead_id,
            "priority_band": priority_band,
            "priority_score": float(priority_score),
            "p_separacion_14d": float(p_sep),
            "p_minuta_60d": float(p_minuta),
            "codigo_proyecto": project,
            "asesor": advisor,
            "canal": channel,
            "medio": medium,
        }
        records.append(
            (
                recommendation_id_for_score(score_id),
                DECISION_SYSTEM,
                evidence_key,
                scored_at,
                model_run_id,
                float(p_minuta),
                recommended_action_for_band(str(priority_band)),
                int(priority_rank),
                json.dumps(context, ensure_ascii=False),
            )
        )

    if not records:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO decision_intelligence.recommendations
              (recommendation_id,decision_system,entity_id,scored_at,model_run_id,
               predicted_probability,recommended_action,priority_rank,context_json)
            VALUES (%s::uuid,%s,%s,%s,%s::uuid,%s,%s,%s,%s::jsonb)
            ON CONFLICT (recommendation_id) DO UPDATE SET
              predicted_probability=EXCLUDED.predicted_probability,
              recommended_action=EXCLUDED.recommended_action,
              priority_rank=EXCLUDED.priority_rank,
              context_json=EXCLUDED.context_json
            """,
            records,
        )
    conn.commit()
    return len(records)


def register_action(
    conn,
    recommendation_id: str,
    action_taken: str,
    action_owner: str,
    action_cost: Decimal | float = 0,
    notes: str | None = None,
) -> str:
    """Registra una acción humana; nunca la ejecuta automáticamente."""
    if not action_taken.strip():
        raise ValueError("action_taken es obligatorio.")
    if not action_owner.strip():
        raise ValueError("action_owner es obligatorio.")
    if Decimal(str(action_cost)) < 0:
        raise ValueError("action_cost no puede ser negativo.")
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT decision_system,entity_id,recommended_action,context_json
               FROM decision_intelligence.recommendations
               WHERE recommendation_id=%s::uuid""",
            (recommendation_id,),
        )
        recommendation = cursor.fetchone()
        if recommendation is None:
            raise RuntimeError(f"No existe recommendation_id={recommendation_id}")
        decision_system, entity_id, recommended_action, context = recommendation
        action_id = str(uuid.uuid4())
        payload = context if isinstance(context, dict) else json.loads(context or "{}")
        action_context = {
            "recommended_action": recommended_action,
            "followed_recommendation": action_taken == recommended_action,
            "recommendation_context": payload,
        }
        cursor.execute(
            """
            INSERT INTO decision_intelligence.actions
              (action_id,recommendation_id,decision_system,entity_id,action_taken,
               action_owner,action_at,action_cost,notes,context_json)
            VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                action_id,
                recommendation_id,
                decision_system,
                entity_id,
                action_taken.strip(),
                action_owner.strip(),
                datetime.now(timezone.utc),
                action_cost,
                notes,
                json.dumps(action_context, ensure_ascii=False),
            ),
        )
    conn.commit()
    return action_id


def refresh_outcomes(conn, cfg: LeadScoringConfig) -> int:
    """Une outcomes maduros a la misma evidencia usada para decidir."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT
              r.entity_id,e.decision_at,e.separacion_14d,e.minuta_60d,e.label_status,
              (SELECT MIN(c.fecha_separacion)::timestamptz
                 FROM core.fact_ciclo_comercial_unidad c
                WHERE c.documento_cliente=e.documento_cliente
                  AND COALESCE(c.codigo_proyecto_ciclo,c.codigo_proyecto_unidad)=e.codigo_proyecto
                  AND c.fecha_separacion>=e.decision_at::date
                  AND c.fecha_separacion<e.decision_at::date+(%s * interval '1 day')) AS fecha_separacion,
              (SELECT MIN(c.fecha_venta)::timestamptz
                 FROM core.fact_ciclo_comercial_unidad c
                WHERE c.documento_cliente=e.documento_cliente
                  AND COALESCE(c.codigo_proyecto_ciclo,c.codigo_proyecto_unidad)=e.codigo_proyecto
                  AND c.fecha_venta>=e.decision_at::date
                  AND c.fecha_venta<e.decision_at::date+(%s * interval '1 day')) AS fecha_minuta
            FROM decision_intelligence.recommendations r
            JOIN features.lead_evidence e ON e.evidence_key=r.entity_id
            WHERE r.decision_system=%s
              AND (e.separacion_14d IS NOT NULL OR e.minuta_60d IS NOT NULL)
            """,
            (cfg.sep_horizon_days, cfg.minuta_horizon_days, DECISION_SYSTEM),
        )
        rows = cursor.fetchall()

    records = []
    for evidence_key, decision_at, sep, minuta, label_status, fecha_sep, fecha_minuta in rows:
        outcomes = (
            ("separacion_14d", sep, cfg.sep_horizon_days, fecha_sep),
            ("minuta_60d", minuta, cfg.minuta_horizon_days, fecha_minuta),
        )
        for outcome_name, value, horizon_days, event_at in outcomes:
            if value is None:
                continue
            observed_at = event_at or decision_at + timedelta(days=horizon_days)
            context = {
                "label_status": label_status,
                "horizon_days": horizon_days,
                "observed_event_at": event_at.isoformat() if event_at else None,
                "negative_observed_at_horizon_close": value == 0,
            }
            records.append(
                (
                    outcome_id_for_evidence(evidence_key, outcome_name),
                    DECISION_SYSTEM,
                    evidence_key,
                    outcome_name,
                    int(value),
                    observed_at,
                    evidence_key,
                    json.dumps(context, ensure_ascii=False),
                )
            )
    if not records:
        return 0
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO decision_intelligence.outcomes
              (outcome_id,decision_system,entity_id,outcome_name,outcome_value,
               outcome_at,source_event_id,context_json)
            VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (outcome_id) DO UPDATE SET
              outcome_value=EXCLUDED.outcome_value,
              outcome_at=EXCLUDED.outcome_at,
              source_event_id=EXCLUDED.source_event_id,
              context_json=EXCLUDED.context_json
            """,
            records,
        )
    conn.commit()
    return len(records)


def measurement_summary(conn) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT decision_date,priority_band,action_status,action_taken,
                   recommendations,actions_recorded,sep_matured,sep_rate,
                   minuta_matured,minuta_rate,total_action_cost
            FROM decision_intelligence.v_lead_action_outcome_performance
            ORDER BY decision_date DESC,priority_band,action_status,action_taken
            """
        )
        names = [item.name for item in cursor.description or []]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
