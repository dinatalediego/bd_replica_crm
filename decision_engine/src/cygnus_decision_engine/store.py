from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from .contracts import Recommendation
from .runtime import SeparationCandidate


CANDIDATE_SQL = """
select
    separation_id::text as separation_id,
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    documento_cliente,
    asesor,
    fecha_separacion,
    observed_at,
    proforma_first_seen_at,
    proforma_age_days,
    eligibility_status,
    eligibility_rule,
    eligibility_window_months,
    days_since_separation,
    days_since_last_interaction,
    interaction_count_14d,
    has_pending_admin_block,
    last_interaction_at,
    interaction_signal_mode,
    admin_signal_mode,
    feature_contract_version,
    quality_status,
    quality_reasons
from features.separation_fall_risk_current
order by observed_at, separation_id
"""


def _normalize_reasons(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


def load_candidates(conn: Connection) -> list[SeparationCandidate]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(CANDIDATE_SQL)
        rows = cur.fetchall()

    candidates: list[SeparationCandidate] = []
    for row in rows:
        quality_status = str(row.get("quality_status") or "OK").upper()
        if quality_status not in {"OK", "WARN", "BLOCKED"}:
            quality_status = "BLOCKED"

        candidates.append(
            SeparationCandidate(
                separation_id=str(row["separation_id"]),
                observed_at=row["observed_at"],
                features={
                    # Commercial identifiers and eligibility evidence are persisted
                    # in feature_snapshot so the worklist is auditable without
                    # joining back to mutable RAW rows.
                    "codigo_proforma": row.get("codigo_proforma"),
                    "codigo_unidad": row.get("codigo_unidad"),
                    "codigo_proyecto": row.get("codigo_proyecto"),
                    "documento_cliente": row.get("documento_cliente"),
                    "asesor": row.get("asesor"),
                    "fecha_separacion": row.get("fecha_separacion"),
                    "proforma_first_seen_at": row.get("proforma_first_seen_at"),
                    "proforma_age_days": row.get("proforma_age_days"),
                    "eligibility_status": row.get("eligibility_status"),
                    "eligibility_rule": row.get("eligibility_rule"),
                    "eligibility_window_months": row.get("eligibility_window_months"),
                    "last_interaction_at": row.get("last_interaction_at"),
                    "interaction_signal_mode": row.get("interaction_signal_mode"),
                    "admin_signal_mode": row.get("admin_signal_mode"),
                    "feature_contract_version": row.get("feature_contract_version"),
                    # Baseline features.
                    "days_since_separation": row["days_since_separation"],
                    "days_since_last_interaction": row["days_since_last_interaction"],
                    "interaction_count_14d": row["interaction_count_14d"],
                    "has_pending_admin_block": row["has_pending_admin_block"],
                },
                quality_status=quality_status,
                quality_reasons=_normalize_reasons(row.get("quality_reasons")),
            )
        )
    return candidates


UPSERT_RECOMMENDATION_SQL = """
insert into decision_intelligence.recommendation (
    recommendation_id,
    decision_key,
    entity_type,
    entity_id,
    observed_at,
    generated_at,
    action,
    score,
    confidence,
    expected_value,
    policy_version,
    explanation,
    quality_status,
    status,
    feature_snapshot,
    evidence
)
values (
    %(recommendation_id)s,
    %(decision_key)s,
    %(entity_type)s,
    %(entity_id)s,
    %(observed_at)s,
    %(generated_at)s,
    %(action)s,
    %(score)s,
    %(confidence)s,
    %(expected_value)s,
    %(policy_version)s,
    %(explanation)s,
    %(quality_status)s,
    %(status)s,
    %(feature_snapshot)s::jsonb,
    %(evidence)s::jsonb
)
on conflict (decision_key, entity_type, entity_id, observed_at, policy_version)
do update set
    recommendation_id = excluded.recommendation_id,
    generated_at = excluded.generated_at,
    action = excluded.action,
    score = excluded.score,
    confidence = excluded.confidence,
    expected_value = excluded.expected_value,
    explanation = excluded.explanation,
    quality_status = excluded.quality_status,
    status = excluded.status,
    feature_snapshot = excluded.feature_snapshot,
    evidence = excluded.evidence
"""


def persist_recommendation(
    conn: Connection,
    recommendation: Recommendation,
    *,
    observed_at: datetime,
    quality_status: str,
    feature_snapshot: dict[str, Any],
) -> None:
    evidence = [item.model_dump(mode="json") for item in recommendation.evidence]
    with conn.cursor() as cur:
        cur.execute(
            UPSERT_RECOMMENDATION_SQL,
            {
                "recommendation_id": recommendation.recommendation_id,
                "decision_key": recommendation.decision_key,
                "entity_type": recommendation.entity_type,
                "entity_id": recommendation.entity_id,
                "observed_at": observed_at,
                "generated_at": recommendation.generated_at,
                "action": recommendation.action,
                "score": recommendation.score,
                "confidence": recommendation.confidence,
                "expected_value": recommendation.expected_value,
                "policy_version": recommendation.policy_version,
                "explanation": recommendation.explanation,
                "quality_status": quality_status,
                "status": recommendation.status,
                "feature_snapshot": json.dumps(feature_snapshot, default=str),
                "evidence": json.dumps(evidence, default=str),
            },
        )


def record_feedback(
    conn: Connection,
    *,
    recommendation_id: str,
    disposition: str,
    actor: str | None = None,
    chosen_action: str | None = None,
    reason: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into decision_intelligence.recommendation_feedback (
                recommendation_id, actor, disposition, chosen_action, reason
            )
            values (%s::uuid, %s, %s, %s, %s)
            """,
            (recommendation_id, actor, disposition, chosen_action, reason),
        )


def record_outcome(
    conn: Connection,
    *,
    recommendation_id: str,
    outcome_name: str,
    outcome_value: Any,
    economic_value: float | None = None,
    observed_at: datetime | None = None,
) -> None:
    observed_at = observed_at or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into decision_intelligence.recommendation_outcome (
                recommendation_id, outcome_name, outcome_value, economic_value, observed_at
            )
            values (%s::uuid, %s, %s::jsonb, %s, %s)
            on conflict (recommendation_id)
            do update set
                outcome_name = excluded.outcome_name,
                outcome_value = excluded.outcome_value,
                economic_value = excluded.economic_value,
                observed_at = excluded.observed_at,
                recorded_at = now()
            """,
            (
                recommendation_id,
                outcome_name,
                json.dumps(outcome_value, default=str),
                economic_value,
                observed_at,
            ),
        )
