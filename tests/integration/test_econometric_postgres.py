"""Full SQL integration suite, an EMPTY disposable DB is required."""
import os
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def test_full_econometric_contract():
    psycopg=pytest.importorskip('psycopg')
    dsn=os.environ.get('ECONOMETRIC_TEST_DSN')
    if not dsn: pytest.skip('Set ECONOMETRIC_TEST_DSN to an empty disposable PostgreSQL DB')
    paths=['tests/integration/evolucion_comercial_fixture.sql','tests/integration/econometric_fixture.sql',
           'sql/99_evolucion_comercial/01_contract.sql','sql/97_commercial_forecasting/01_evidence.sql']
    contracts=[f'sql/100_econometria/{p}.sql' for p in ['01_tables','02_capture','03_datasets','04_evaluation']]
    with psycopg.connect(dsn) as conn:
        try:
            for path in paths+contracts+contracts:
                conn.execute((ROOT/path).read_text(),prepare=False)
            for fn in ['refresh_evolucion_comercial()','capture_econometric_events()',
                       'capture_econometric_current()','backfill_econometric_prices()',
                       'backfill_econometric_stock()','build_econometric_datasets(true)']:
                conn.execute('SELECT analytics.'+fn)
            conn.execute((ROOT/'tests/integration/econometric_assertions.sql').read_text(),prepare=False)
        finally:
            conn.rollback()
