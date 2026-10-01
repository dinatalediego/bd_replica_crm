from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sync_uses_fresh_redshift_connection_per_attempt() -> None:
    code = (ROOT / "src" / "replica_cygnus" / "cli.py").read_text(encoding="utf-8")

    assert 'REDSHIFT_SYNC_MAX_ATTEMPTS' in code
    assert 'REDSHIFT_SYNC_RETRY_SECONDS' in code
    assert 'source = connect_redshift(settings)' in code
    assert 'for attempt in range(1, max_attempts + 1)' in code
    assert 'source.close()' in code
    assert '_is_transient_source_error' in code


def test_catalog_reconnects_instead_of_fallback_on_timeout() -> None:
    code = (ROOT / "src" / "replica_cygnus" / "catalog.py").read_text(encoding="utf-8")

    assert '_is_connection_timeout' in code
    assert 'se requiere reconexión antes de reintentar' in code
    assert 'raise' in code


def test_raw_failure_still_blocks_downstream_dw_promotion() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8")

    raw_pos = code.index('"01_raw_sync"')
    schema_pos = code.index('"02_schema_sync"')
    assert raw_pos < schema_pos
    assert 'raise StepFailure(step, completed.returncode)' in code
