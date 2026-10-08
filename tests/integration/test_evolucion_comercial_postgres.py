"""Synthetic SQL contract checks; disposable PostgreSQL only."""
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_evolucion_contract():
    psycopg = pytest.importorskip('psycopg')
    dsn = os.environ.get('EVOLUCION_TEST_DSN')
    if not dsn:
        pytest.skip('Set EVOLUCION_TEST_DSN to an empty disposable PostgreSQL database')
    with psycopg.connect(dsn) as conn:
        try:
            for path in ['tests/integration/evolucion_comercial_fixture.sql',
                         'sql/99_evolucion_comercial/01_contract.sql',
                         'sql/99_evolucion_comercial/01_contract.sql',
                         'tests/integration/evolucion_comercial_assertions.sql']:
                conn.execute((ROOT/path).read_text(), prepare=False)
        finally:
            conn.rollback()
