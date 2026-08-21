from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "profile_interaction_contract.py"
DOC = ROOT / "decision_engine" / "docs" / "INTERACTION_FEATURE_CONTRACT_V0.md"


def _script() -> str:
    return " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())


def _doc() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").lower().split())


def test_interaction_contract_discovers_schema_instead_of_assuming_event_time() -> None:
    text = _script()
    assert "information_schema.columns" in text
    assert "discovery_only_not_certified" in text
    assert "date_candidates" in text
    assert "key_candidates" in text


def test_interaction_contract_requires_asof_and_join_safety_before_features() -> None:
    text = _doc()
    assert "<= t" in text
    assert "many-to-many join inflation" in text
    assert "interaction identity" in text
    assert "historical completeness" in text
    assert "current/historical parity" in text


def test_candidate_interaction_features_are_behavioral_and_interpretable() -> None:
    text = _doc()
    assert "days_since_last_interaction" in text
    assert "interaction_count_7d" in text
    assert "interaction_count_14d" in text
    assert "interaction_count_30d" in text
    assert "interaction_velocity_7d_vs_30d" in text


def test_update_timestamp_is_not_accepted_as_event_time_by_default() -> None:
    text = _doc()
    assert "fecha_actualizacion" in text
    assert "edit timestamp" in text
    assert "do not tune model hyperparameters aggressively" in text
