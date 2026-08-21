from __future__ import annotations

from .contracts import DecisionContext, Evidence, Recommendation


POLICY_VERSION = "separation-fall-risk-baseline-v0.1.0"


def separation_fall_risk_baseline(context: DecisionContext) -> Recommendation:
    """Baseline explicable para priorizar separaciones activas.

    Espera, cuando estén disponibles:
      - days_since_separation
      - days_since_last_interaction
      - interaction_count_14d
      - has_pending_admin_block

    No pretende ser el modelo final. Es el benchmark operativo que cualquier
    modelo posterior debe superar out-of-time.
    """
    if context.quality_status == "BLOCKED":
        return Recommendation.blocked(context, policy_version=POLICY_VERSION)

    f = context.features
    days_sep = int(f.get("days_since_separation", 0) or 0)
    days_contact = int(f.get("days_since_last_interaction", 0) or 0)
    interactions = int(f.get("interaction_count_14d", 0) or 0)
    admin_block = bool(f.get("has_pending_admin_block", False))

    score = 0.0
    reasons: list[str] = []

    if days_sep >= 21:
        score += 0.35
        reasons.append("separación con 21+ días")
    elif days_sep >= 10:
        score += 0.20
        reasons.append("separación con 10+ días")

    if days_contact >= 7:
        score += 0.35
        reasons.append("7+ días sin interacción")
    elif days_contact >= 3:
        score += 0.20
        reasons.append("3+ días sin interacción")

    if interactions == 0:
        score += 0.20
        reasons.append("sin interacciones en 14 días")

    if admin_block:
        score += 0.10
        reasons.append("bloqueo administrativo pendiente")

    score = min(score, 1.0)

    if score >= 0.65:
        action = "urgent_follow_up"
    elif score >= 0.35:
        action = "follow_up"
    else:
        action = "monitor"

    explanation = ", ".join(reasons) if reasons else "sin señales fuertes en el baseline"

    evidence = [
        Evidence(name="days_since_separation", value=days_sep),
        Evidence(name="days_since_last_interaction", value=days_contact),
        Evidence(name="interaction_count_14d", value=interactions),
        Evidence(name="has_pending_admin_block", value=admin_block),
    ]

    return Recommendation(
        decision_key=context.decision_key,
        entity_type=context.entity_type,
        entity_id=context.entity_id,
        generated_at=context.observed_at,
        action=action,
        score=score,
        confidence=None,
        expected_value=None,
        policy_version=POLICY_VERSION,
        explanation=explanation,
        evidence=evidence,
    )
