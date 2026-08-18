import pytest

from cygnus_decision_engine.cli import _separation_risk_health_is_unsafe


def healthy(**overrides):
    base = {
        "universe_candidates": 120,
        "eligible_candidates": 20,
        "candidates": 20,
        "distinct_candidates": 20,
        "duplicate_candidates": 0,
        "excluded_proforma_older_than_3_months": 95,
        "excluded_missing_proforma_date": 5,
        "excluded_proforma_after_observed_at": 0,
        "excluded_missing_observed_at": 0,
        "current_outside_proforma_recency_window": 0,
        "quality_blocked": 0,
        "missing_observed_at": 0,
    }
    base.update(overrides)
    return base


def test_old_and_missing_date_exclusions_do_not_contaminate_current_candidates() -> None:
    # Old proformas are intentionally excluded; missing source dates are reported
    # as completeness debt. Neither should poison an otherwise safe eligible set.
    assert _separation_risk_health_is_unsafe(healthy()) is False


@pytest.mark.parametrize(
    "field",
    [
        "duplicate_candidates",
        "quality_blocked",
        "missing_observed_at",
        "current_outside_proforma_recency_window",
        "excluded_proforma_after_observed_at",
        "excluded_missing_observed_at",
    ],
)
def test_hard_quality_failures_block_decisions(field: str) -> None:
    assert _separation_risk_health_is_unsafe(healthy(**{field: 1})) is True


def test_candidate_count_must_equal_eligible_and_distinct_count() -> None:
    assert _separation_risk_health_is_unsafe(healthy(eligible_candidates=21)) is True
    assert _separation_risk_health_is_unsafe(healthy(distinct_candidates=19)) is True


def test_every_universe_row_must_land_in_exactly_one_eligibility_bucket() -> None:
    assert _separation_risk_health_is_unsafe(healthy(universe_candidates=121)) is True
