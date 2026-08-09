import pandas as pd

from replica_cygnus.decision_intelligence.learning import evaluate_decisions


def test_learning_report():
    df = pd.DataFrame(
        {
            "predicted_probability": [0.2, 0.8],
            "action_taken": [0, 1],
            "outcome": [0, 1],
            "realized_incremental_value": [0, 100],
        }
    )
    report = evaluate_decisions(df)
    assert report.observations == 2
    assert report.action_rate == 0.5
    assert report.realized_incremental_value == 100
