from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "08_training_outcome_contract.sql"


def test_department_transfer_is_separate_competing_event() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())

    assert "'transfer_unit'" in sql
    assert "known_department_transfer_post_outcome" in sql
    assert "training_target_fall_before_conversion" in sql
    assert "then null::integer" in sql


def test_transfer_evidence_cannot_be_live_feature() -> None:
    sql = SQL.read_text(encoding="utf-8").lower()

    assert "target_only_post_outcome_governance" in sql
    assert "false::boolean as transfer_evidence_live_feature_eligible" in sql


def test_training_health_blocks_transfer_label_leakage() -> None:
    sql = SQL.read_text(encoding="utf-8").lower()

    assert "v_separation_fall_training_outcome_health" in sql
    assert "transfer_rows_leaking_into_binary_target" in sql
    assert "eligible_with_null_target" in sql
    assert "trainable_fall_rate" in sql
