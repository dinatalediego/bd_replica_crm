from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("ABSORCION_TEST_DSN")
    if not dsn:
        pgserver = pytest.importorskip("pgserver")
        server = pgserver.get_server(tempfile.mkdtemp(prefix="model-dq-test-"), cleanup_mode="delete")
        dsn = server.get_uri()
    with psycopg.connect(dsn) as conn:
        # All DDL and fixtures are rolled back; never target a production database.
        conn.execute("CREATE SCHEMA model_control")
        yield conn
        conn.rollback()


def test_quality_contract_is_idempotent_and_blocks_incomplete_run(db):
    migration = (ROOT / "sql/115_model_data_quality_gates/01_contract.sql").read_text(encoding="utf-8")
    with db.cursor() as cur:
        cur.execute(migration, prepare=False)
        cur.execute(migration, prepare=False)

    assert db.execute("SELECT count(*) FROM model_control.data_quality_test_catalog").fetchone()[0] == 31
    states = db.execute("SELECT count(*) FROM model_control.v_model_data_quality_latest_gate WHERE data_quality_status = 'NO_RUN'").fetchone()[0]
    assert states == 4

    cur = db.execute("""
        INSERT INTO model_control.data_quality_suite_run
            (suite_key, dataset_key, run_status, runner_version, completed_at)
        VALUES ('commercial_forecast', 'forecast_issue_registry', 'PASS', 'test', now())
        RETURNING run_id
    """)
    run_id = cur.fetchone()[0]
    db.execute("""
        INSERT INTO model_control.data_quality_test_result
            (run_id, test_id, result_status, details)
        VALUES (%s, 'FC_SCHEMA', 'PASS', 'synthetic fixture')
    """, (run_id,))
    row = db.execute("""
        SELECT expected_tests, executed_tests, failed_tests, data_quality_status
        FROM model_control.v_model_data_quality_latest_gate
        WHERE dataset_key = 'forecast_issue_registry'
    """).fetchone()
    assert row == (8, 1, 0, "BLOCK")

