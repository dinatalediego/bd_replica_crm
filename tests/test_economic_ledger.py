import pytest

from replica_cygnus.decision_intelligence.economic_ledger import (
    EconomicValueEntry,
    expected_economic_value_entry,
)
from replica_cygnus.decision_intelligence.economics import EconomicPolicy


def test_expected_economic_value_entry_matches_existing_engine_math():
    policy = EconomicPolicy(
        value_if_success=1000,
        loss_if_failure=100,
        action_cost=20,
        opportunity_cost=10,
        treatment_effect=0.10,
    )

    entry = expected_economic_value_entry(
        decision_id="DEC-001",
        value_name="lead_expected_margin",
        probability_success=0.50,
        policy=policy,
        confidence_pct=75,
        horizon_days=30,
        value_type="MARGIN",
    )

    assert entry.value_stage == "EXPECTED"
    assert entry.baseline_value == pytest.approx(450)
    assert entry.comparison_value == pytest.approx(530)
    assert entry.net_incremental_value == pytest.approx(80)
    assert entry.direct_cost == pytest.approx(20)
    assert entry.opportunity_cost == pytest.approx(10)
    assert entry.confidence_adjusted_value == pytest.approx(60)
    assert entry.probability == pytest.approx(0.50)


def test_economic_value_entry_rejects_invalid_confidence():
    entry = EconomicValueEntry(
        decision_id="DEC-001",
        value_name="pricing_value",
        value_stage="EXPECTED",
        value_type="REVENUE",
        currency="PEN",
        baseline_value=100,
        comparison_value=120,
        direct_cost=0,
        opportunity_cost=0,
        net_incremental_value=20,
        confidence_pct=101,
    )

    with pytest.raises(ValueError, match="confidence_pct"):
        entry.validate()


def test_db_params_do_not_double_subtract_costs():
    policy = EconomicPolicy(
        value_if_success=1000,
        action_cost=25,
        opportunity_cost=5,
        treatment_effect=0.05,
    )
    entry = expected_economic_value_entry(
        decision_id="DEC-002",
        value_name="conversion_uplift",
        probability_success=0.40,
        policy=policy,
    )

    params = entry.as_db_params()
    assert params["net_incremental_value"] == pytest.approx(
        params["comparison_value"] - params["baseline_value"]
    )
    assert params["direct_cost"] == 25
    assert params["opportunity_cost"] == 5
