from replica_cygnus.decision_intelligence.economics import EconomicPolicy, economic_value


def test_economic_value_uses_incremental_effect_and_costs():
    policy = EconomicPolicy(
        value_if_success=1000,
        loss_if_failure=100,
        action_cost=20,
        opportunity_cost=10,
        treatment_effect=0.1,
    )
    out = economic_value(0.5, policy)
    assert out["expected_value_no_action"] == 450
    assert round(out["expected_value_with_action"], 8) == 530
    assert round(out["expected_incremental_value"], 8) == 80


def test_entity_specific_cate_changes_value():
    policy = EconomicPolicy(value_if_success=1000, action_cost=10)
    low = economic_value(0.5, policy, treatment_effect=0.01)
    high = economic_value(0.5, policy, treatment_effect=0.20)
    assert high["expected_incremental_value"] > low["expected_incremental_value"]
