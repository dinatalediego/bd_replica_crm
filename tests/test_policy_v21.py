from replica_cygnus.lead_scoring.policy_v21 import (
    PolicyRunConfig,
    experiment_id,
    policy_run_id,
)


def test_policy_v21_exact_targets():
    cfg = PolicyRunConfig(cohort_size=100, treatment_share=0.80)
    assert cfg.treatment_target_n == 80
    assert cfg.control_target_n == 20


def test_policy_v21_ids_are_deterministic():
    assert experiment_id() == experiment_id()
    assert policy_run_id("pilot_01") == policy_run_id("pilot_01")
    assert policy_run_id("pilot_01") != policy_run_id("pilot_02")


def test_policy_v21_rejects_invalid_share():
    cfg = PolicyRunConfig(treatment_share=1.0)
    try:
        cfg.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
