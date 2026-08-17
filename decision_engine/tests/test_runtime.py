from datetime import datetime, timezone

from cygnus_decision_engine.runtime import SeparationCandidate, score_candidates


def candidate(entity_id: str, **features):
    return SeparationCandidate(
        separation_id=entity_id,
        observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        features=features,
    )


def test_worklist_prioritizes_highest_score():
    results = score_candidates(
        [
            candidate(
                "LOW",
                days_since_separation=1,
                days_since_last_interaction=1,
                interaction_count_14d=3,
                has_pending_admin_block=False,
            ),
            candidate(
                "HIGH",
                days_since_separation=25,
                days_since_last_interaction=10,
                interaction_count_14d=0,
                has_pending_admin_block=True,
            ),
        ]
    )
    assert results[0].entity_id == "HIGH"
    assert results[0].action == "urgent_follow_up"


def test_blocked_candidate_is_never_prioritized_as_active():
    blocked = SeparationCandidate(
        separation_id="BLOCKED",
        observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        features={"days_since_separation": 99},
        quality_status="BLOCKED",
        quality_reasons=("cycle not reconciled",),
    )
    active = candidate(
        "ACTIVE",
        days_since_separation=12,
        days_since_last_interaction=4,
        interaction_count_14d=1,
        has_pending_admin_block=False,
    )

    results = score_candidates([blocked, active])
    assert results[0].entity_id == "ACTIVE"
    assert results[-1].status == "BLOCKED"
