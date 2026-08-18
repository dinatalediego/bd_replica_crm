from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "11_training_readiness_audit.sql"


def _sql() -> str:
    return " ".join(SQL.read_text(encoding="utf-8").lower().split())


def test_readiness_audit_exposes_class_dependent_representation() -> None:
    sql = _sql()
    assert "represented_lifecycle_coverage" in sql
    assert "represented_fall_lifecycle_coverage" in sql
    assert "represented_conversion_lifecycle_coverage" in sql
    assert "source_lifecycle_fall_rate" in sql
    assert "represented_lifecycle_fall_rate" in sql
    assert "snapshot_fall_rate" in sql


def test_readiness_audit_distinguishes_pre_observation_landmarks_from_missing_data() -> None:
    sql = _sql()
    assert "proforma_not_yet_observed_rows" in sql
    assert "lifecycles_with_pre_observation_landmarks" in sql
    assert "median_days_until_proforma_observed" in sql
    assert "missing_proforma_first_seen_rows" in sql


def test_readiness_audit_reconciles_all_landmark_rows() -> None:
    sql = _sql()
    assert "expected_landmark_audit_rows" in sql
    assert "landmark_expansion_accounting_gap" in sql
    assert "eligibility_bucket_accounting_gap" in sql
    assert "source_trainable_lifecycles * 9" in sql


def test_readiness_audit_profiles_fast_outcomes_and_temporal_drift() -> None:
    sql = _sql()
    assert "source_same_day_conversions" in sql
    assert "source_conversions_within_7d" in sql
    assert "v_separation_fall_training_period_profile" in sql
    assert "v_separation_fall_training_landmark_profile" in sql


def test_model_estimand_is_explicitly_conditional_on_snapshot_eligibility() -> None:
    sql = _sql()
    assert "conditional_risk_among_opportunities_still_eligible_at_snapshot" in sql
    assert "do_not_compare_snapshot_prevalence_directly_to_all_separations" in sql
