from replica_cygnus.decision_intelligence.contracts import DecisionContract


def test_contract_validates():
    contract = DecisionContract.from_dict(
        {
            "name": "lead_priority",
            "objective": "Priorizar",
            "decision_unit": "lead",
            "decision_owner": "supervisor",
            "available_actions": ["CALL", "NO_ACTUAR"],
            "target": "separacion_14d",
            "prediction_horizon_days": 14,
            "causal_estimand": "CATE",
            "primary_value_metric": "valor_esperado",
            "feedback_outcome": "separacion_14d",
        }
    )
    assert contract.name == "lead_priority"
    assert contract.prediction_horizon_days == 14
