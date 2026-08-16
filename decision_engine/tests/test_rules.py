from datetime import datetime, timezone

from cygnus_decision_engine.contracts import DecisionContext
from cygnus_decision_engine.rules import separation_fall_risk_baseline


def make_context(**features):
    return DecisionContext(
        decision_key="separation_fall_risk",
        entity_type="separation",
        entity_id="SEP-001",
        observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        features=features,
    )


def test_urgent_follow_up_for_old_inactive_separation():
    rec = separation_fall_risk_baseline(
        make_context(
            days_since_separation=25,
            days_since_last_interaction=9,
            interaction_count_14d=0,
            has_pending_admin_block=False,
        )
    )
    assert rec.action == "urgent_follow_up"
    assert rec.score >= 0.65


def test_monitor_for_recent_active_separation():
    rec = separation_fall_risk_baseline(
        make_context(
            days_since_separation=2,
            days_since_last_interaction=1,
            interaction_count_14d=4,
            has_pending_admin_block=False,
        )
    )
    assert rec.action == "monitor"
    assert rec.score == 0.0


def test_quality_gate_blocks_decision():
    ctx = make_context(days_since_separation=40)
    ctx.quality_status = "BLOCKED"
    ctx.quality_reasons = ["commercial cycle is not reconciled"]

    rec = separation_fall_risk_baseline(ctx)

    assert rec.status == "BLOCKED"
    assert rec.action == "do_not_decide"
