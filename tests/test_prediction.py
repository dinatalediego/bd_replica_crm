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


def test_prediction_restores_rare_event_training_prior():
    n = 1000
    df = pd.DataFrame(
        {
            "x": [0.0] * n,
            "segment": ["same"] * n,
            "y": [1] * 10 + [0] * (n - 10),
        }
    )
    model = train_binary_logistic_model(df, "y", ["x"], ["segment"])
    probabilities = model.predict_probability(df)
    assert abs(float(probabilities.mean()) - 0.01) < 0.002
    assert model.prior_log_odds_offset < 0
