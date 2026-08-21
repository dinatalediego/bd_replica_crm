from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "profile_interaction_contract_stage2.py"


def _text() -> str:
    return " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())


def test_stage2_does_not_auto_certify_event_time() -> None:
    text = _text()
    assert "review_required_do_not_auto_certify" in text
    assert "fecha_actualizacion and _etl_loaded_at are not eligible" in text


def test_stage2_profiles_direct_proforma_linkage() -> None:
    text = _text()
    assert "interaction_rows_matching_core_proforma" in text
    assert "interaction_proformas_with_multiple_training_lifecycles" in text
    assert "prefer direct codigo_proforma attribution" in text


def test_stage2_profiles_identity_and_temporal_coverage() -> None:
    text = _text()
    assert "duplicate_id_groups" in text
    assert "duplicate_id_proforma_groups" in text
    assert "timestamp_year_coverage.csv" in text
    assert "fecha_creacion" in text
    assert "fecha_programada" in text


def test_stage2_keeps_asof_gate_explicit() -> None:
    text = _text()
    assert "interaction_event_at <= snapshot_at" in text
