from replica_cygnus.decision_intelligence.economics import EconomicPolicy
from replica_cygnus.decision_intelligence.engine import DecisionEngine


def test_engine_respects_capacity_and_ranks_cate():
    engine = DecisionEngine(
        action_name="CALL",
        policy=EconomicPolicy(value_if_success=1000, action_cost=10),
        min_incremental_value=1,
        max_actions=2,
    )
    rows = engine.rank([("a", 0.2, 0.02), ("b", 0.9, 0.08), ("c", 0.5, 0.15)])
    assert sum(x.recommended_action == "CALL" for x in rows) == 2
    assert rows[0].entity_id == "c"
    assert [x.priority_rank for x in rows] == [1, 2, 3]
