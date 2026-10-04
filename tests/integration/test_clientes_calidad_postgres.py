"""Synthetic disposable PostgreSQL. Never point CLIENTES_CALIDAD_TEST_DSN at Medallio."""
import importlib.util
import os
from pathlib import Path
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / 'sql/90_clientes_calidad/01_clientes_calidad.sql'
spec = importlib.util.spec_from_file_location('refresh_dq', ROOT / 'scripts/refresh_clientes_calidad.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def db():
    psycopg = pytest.importorskip('psycopg')
    dsn = os.environ.get('CLIENTES_CALIDAD_TEST_DSN') or os.environ.get('ABSORCION_TEST_DSN')
    if not dsn:
        pgserver = pytest.importorskip('pgserver')
        server = pgserver.get_server(tempfile.mkdtemp(prefix='clientes-dq-test-'), cleanup_mode='delete')
        dsn = server.get_uri()
    with psycopg.connect(dsn) as conn:
        # Refuse an occupied schema instead of dropping somebody's actual data.
        conn.execute('CREATE SCHEMA raw_cygnus; CREATE SCHEMA staging')
        conn.execute('''CREATE TABLE raw_cygnus.clientes (
            id text, nombres text, apellidos text, documento text,
            celulares text, telefono text, email text, nombre_proyecto text,
            vendedor text, medio_captacion text, estado text,
            _etl_loaded_at timestamptz DEFAULT now(), _etl_source_run_id text)''')
        conn.execute(SQL.read_text(), prepare=False)
        yield conn
        conn.rollback()


def add(db, identity='1', phone='+51 987 654 321'):
    db.execute('''INSERT INTO raw_cygnus.clientes
        (id,nombres,apellidos,documento,celulares,telefono,email,nombre_proyecto,vendedor,medio_captacion,estado)
        VALUES (%s,'Ana','Demo','12345678',%s,'1234567','ANA@EXAMPLE.TEST','DEMO','Asesor','Digital','Lead')''',
        (identity, phone))


def call(db):
    db.execute('CALL staging.refresh_clientes_calidad()')
    return db.execute('''SELECT inserted_rows, updated_rows, deleted_rows, unchanged_rows
        FROM staging.clientes_calidad_refresh_runs ORDER BY run_id DESC LIMIT 1''').fetchone()


def rows(db):
    return dict(db.execute('SELECT source_id, to_jsonb(t) FROM staging.clientes_calidad t'))


def test_bootstrap_then_unchanged_and_etl_only_changes_are_noop(db):
    add(db)
    assert call(db) == (1, 0, 0, 0)
    db.execute("UPDATE staging.clientes_calidad SET refreshed_at='2000-01-01'")
    initial = rows(db)
    assert call(db) == (0, 0, 0, 1)
    db.execute("UPDATE raw_cygnus.clientes SET _etl_loaded_at=now()+interval '1 day', _etl_source_run_id='next'")
    assert call(db) == (0, 0, 0, 1)
    assert rows(db) == initial  # Including refreshed_at and hash.


def test_new_modified_deleted_and_missing_target_match_full_rebuild(db):
    add(db, '1'); add(db, '2'); add(db, '3')
    call(db)
    original = rows(db)
    db.execute("UPDATE raw_cygnus.clientes SET celulares='+1 202 555 0144' WHERE id='1'")
    db.execute("DELETE FROM raw_cygnus.clientes WHERE id='2'")
    add(db, '4')
    assert call(db) == (1, 1, 1, 1)
    current = rows(db)
    assert current['3'] == original['3']
    assert current['1']['dq_estado_celular'] == 'Celular extranjero'
    db.execute("DELETE FROM staging.clientes_calidad WHERE source_id='4'")
    assert call(db) == (1, 0, 0, 2)
    expected = rows(db)
    db.execute("SELECT set_config('medallio.clientes_calidad_full','on',true)")
    assert call(db) == (0, 3, 0, 0)
    rebuilt = rows(db)
    for value in (*expected.values(), *rebuilt.values()):
        value.pop('refreshed_at')
    assert expected == rebuilt


def test_phone_priority_foreign_format_dni_and_score(db):
    add(db, '1'); add(db, '2', '+1 202 555 0144'); add(db, '3', '123')
    add(db, '4', None); add(db, '5', '')
    db.execute("UPDATE raw_cygnus.clientes SET documento=NULL WHERE id='3'")
    call(db)
    r = rows(db)
    assert r['1']['dq_celular_limpio'] == '987654321'
    assert r['1']['dq_score_cliente'] == 100
    assert r['2']['dq_estado_celular'] == 'Celular extranjero'
    assert r['2']['dq_celular_ok'] is True
    assert r['3']['dq_documento_ok_estado'] == 'revisar dni'
    assert r['3']['dq_estado_celular'] == 'Revisar formato'
    assert r['3']['dq_score_cliente'] == 80  # Valid email preserves contact.
    assert r['4']['dq_fuente_celular'] == 'telefono'
    assert r['5']['dq_fuente_celular'] == 'celulares'  # Blank must not silently fall back.
    assert r['5']['dq_estado_celular'] == 'Vacío'


def test_singular_phone_used_only_when_plural_column_absent(db):
    db.execute('ALTER TABLE raw_cygnus.clientes RENAME celulares TO celular')
    db.execute("INSERT INTO raw_cygnus.clientes(id,celular,telefono) VALUES ('1','987654321','1234567')")
    call(db)
    assert rows(db)['1']['dq_fuente_celular'] == 'celular'


@pytest.mark.parametrize('bad_id', [None, '', '1'])
def test_invalid_raw_id_rolls_back_and_keeps_previous_state(db, bad_id):
    import psycopg
    add(db); call(db)
    initial = rows(db)
    add(db, bad_id)
    with pytest.raises(psycopg.Error, match='id nulo/vacio|id duplicado'):
        with db.transaction():
            call(db)
    assert rows(db) == initial
    assert db.execute('SELECT count(*) FROM staging.clientes_calidad_refresh_runs').fetchone()[0] == 1


def test_rule_change_rebuilds_once(db):
    add(db); call(db)
    db.execute('''CREATE OR REPLACE FUNCTION staging.dq_normalize_text(value text)
        RETURNS text LANGUAGE sql IMMUTABLE AS $$
        SELECT NULLIF(regexp_replace(btrim(value), '[[:space:]]+', ' ', 'g'), '') -- v2
        $$''')
    assert call(db) == (0, 1, 0, 0)
    assert call(db) == (0, 0, 0, 1)


def test_empty_source_removes_stale_target(db):
    add(db); call(db)
    db.execute('DELETE FROM raw_cygnus.clientes')
    assert call(db) == (0, 0, 1, 0)
    assert rows(db) == {}
    assert call(db) == (0, 0, 0, 0)


def test_migration_preserves_legacy_table_and_repairs_duplicate_target(db):
    add(db); call(db)
    db.execute('INSERT INTO staging.clientes_calidad SELECT * FROM staging.clientes_calidad')
    db.execute(SQL.read_text(), prepare=False)  # Idempotent installation; no truncate.
    assert db.execute('SELECT count(*) FROM staging.clientes_calidad').fetchone()[0] == 2
    assert call(db) == (0, 1, 0, 0)
    assert len(rows(db)) == 1


def test_python_gate_rolls_back_changes_before_commit(db):
    add(db); call(db)
    initial = rows(db)
    db.execute("UPDATE raw_cygnus.clientes SET nombres='Changed'")
    db.execute('DROP VIEW staging.v_clientes_calidad_health')
    db.execute('''CREATE VIEW staging.v_clientes_calidad_health AS
        SELECT 999::bigint AS filas_raw, count(*) AS filas_staging FROM staging.clientes_calidad''')
    with pytest.raises(RuntimeError, match='NO aprobado'):
        runner.refresh(db)
    assert rows(db) == initial
    assert db.execute('SELECT count(*) FROM staging.clientes_calidad_refresh_runs').fetchone()[0] == 1


def test_advisory_lock_rejects_concurrent_refresh(db):
    import psycopg
    add(db)
    with psycopg.connect(db.info.dsn) as other:
        other.execute('SELECT pg_advisory_xact_lock(9042026,2)')
        with pytest.raises(psycopg.Error, match='otro refresh sigue activo'):
            with db.transaction():
                call(db)
    assert call(db) == (1, 0, 0, 0)


def test_python_refresh_reports_success_and_second_run_noop(db, capsys):
    add(db)
    assert runner.refresh(db) == 0
    assert runner.refresh(db) == 0
    output = capsys.readouterr().out
    assert 'Gate clientes_calidad APROBADO' in output
    assert 'mode=incremental' in output
    assert 'unchanged_rows=1' in output
