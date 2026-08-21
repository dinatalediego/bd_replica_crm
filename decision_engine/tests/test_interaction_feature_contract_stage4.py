from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'profile_interaction_contract_stage4.py'


def _text() -> str:
    return ' '.join(SCRIPT.read_text(encoding='utf-8').lower().split())


def test_stage4_profiles_composite_identity_candidates() -> None:
    text = _text()
    assert 'tipo,id' in text
    assert 'tipo,id,fecha_creacion' in text
    assert 'identity_candidate_health.csv' in text


def test_stage4_reconstructs_update_timestamp_with_time_component() -> None:
    text = _text()
    assert 'hora_actualizacion' in text
    assert 'fecha_actualizacion::timestamp + hora_actualizacion::time' in text
    assert 'update_clock_health.csv' in text


def test_stage4_does_not_auto_certify_event_time() -> None:
    text = _text()
    assert 'stage4_profiled_not_certified' in text
    assert "'evento': 'exclude from behavioral v1" in text
    assert "'_etl_loaded_at': 'never behavioral event time'" in text


def test_stage4_blocks_system_events_and_customer_fanout() -> None:
    text = _text()
    assert 'creación de cliente' in text
    assert 'creación de proforma' in text
    assert 'never fan-out multi-lifecycle clients' in text
    assert 'interaction_event_at <= snapshot_at' in text
