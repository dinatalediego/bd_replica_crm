from datetime import datetime, timezone

from cygnus_decision_engine import DecisionContext, separation_fall_risk_baseline


context = DecisionContext(
    decision_key="separation_fall_risk",
    entity_type="separation",
    entity_id="DEMO-SEP-001",
    observed_at=datetime.now(timezone.utc),
    features={
        "days_since_separation": 24,
        "days_since_last_interaction": 8,
        "interaction_count_14d": 0,
        "has_pending_admin_block": True,
    },
)

recommendation = separation_fall_risk_baseline(context)
print(recommendation.model_dump_json(indent=2))
