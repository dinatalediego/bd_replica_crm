import pandas as pd

from replica_cygnus.decision_intelligence.prediction import train_binary_logistic_model


def test_prediction_outputs_probabilities():
    df = pd.DataFrame(
        {
            "x": list(range(20)),
            "segment": ["a", "b"] * 10,
            "y": [0] * 8 + [1] * 12,
        }
    )
    model = train_binary_logistic_model(df, "y", ["x"], ["segment"], validation=df)
    p = model.predict_probability(df)
    assert len(p) == len(df)
    assert p.between(0, 1).all()
    assert model.brier is not None
