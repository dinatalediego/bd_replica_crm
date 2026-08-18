from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "profile_interaction_contract_stage3.py"


def _text() -> str:
    return " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())


def test_stage3_separates_missing_proforma_from_bad_proforma_match() -> None:
    text = _text()
    assert "rows_without_proforma" in text
    assert "rows_with_proforma_unmatched_core" in text
    assert "stage2 interaction_rows_unmatched_to_core_proforma included the null codigo_proforma bucket" in text


def test_stage3_does_not_auto_attribute_customer_events_to_all_lifecycles() -> None:
    text = _text()
    assert "no_proforma_rows_ambiguous_multi_lifecycle_client" in text
    assert "never fan one customer interaction out to every proforma" in text
    assert "temporal attribution after event-time certification" in text


def test_stage3_keeps_event_time_uncertified() -> None:
    text = _text()
    assert '"event_time_status": "not_certified"' in text
    assert "timestamp_pair_semantics.csv" in text


def test_stage3_profiles_identity_and_event_taxonomy() -> None:
    text = _text()
    assert "duplicate_id_samples.csv" in text
    assert "category_top_values.csv" in text
    assert "duplicate id groups block id-only interaction identity certification" in text
