import pandas as pd

from replica_cygnus.decision_intelligence.causal import estimate_difference_in_differences


def test_did_recovers_known_effect():
    rows = []
    for treated in [0, 1]:
        for post in [0, 1]:
            for i in range(20):
                y = 10 + 2 * treated + 3 * post + 5 * treated * post + (i % 3) * 0.01
                rows.append({"y": y, "treated": treated, "post": post})
    result = estimate_difference_in_differences(pd.DataFrame(rows), "y", "treated", "post")
    assert abs(result.treatment_effect - 5) < 0.1
