"""Synthetic PostgreSQL only. ABSORCION_TEST_DSN must point to a disposable DB."""
import os
from pathlib import Path
from datetime import date

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    psycopg = pytest.importorskip('psycopg')
    dsn = os.environ.get('ABSORCION_TEST_DSN')
    server = None
    if not dsn:
        pgserver = pytest.importorskip('pgserver')
        import tempfile
        server = pgserver.get_server(tempfile.mkdtemp(prefix='absorcion-test-'), cleanup_mode='delete')
        dsn = server.get_uri()
    with psycopg.connect(dsn) as conn:
        # Rollback isolates every test; refuse an existing schema rather than delete it.
        conn.execute('CREATE SCHEMA analytics; CREATE SCHEMA core; CREATE SCHEMA observability; CREATE SCHEMA raw_cygnus; CREATE SCHEMA etl_control')
        conn.execute('''CREATE TABLE core.dim_unidad (
            codigo_unidad text PRIMARY KEY, codigo_proyecto text, nombre_unidad text,
            tipo_unidad text, estado_comercial text, codigo_subdivision text)''')
        conn.execute('''CREATE TABLE raw_cygnus.procesos (
            id bigserial PRIMARY KEY,codigo_proforma text,codigo_unidad text,
            nombre text,estado text DEFAULT 'Activo',fecha_inicio date,nombre_flujo text);
            CREATE TABLE raw_cygnus.datos_extras (id bigserial PRIMARY KEY,codigo text,
            entidad text,nombre text,valor text,fecha_actualizacion timestamp)''')
        conn.execute('CREATE VIEW analytics.v_ciclo_comercial_reconciliado AS SELECT 1 AS legacy_column')
        for path in ['sql/20_absorption_phase_b/01_control_and_functions.sql',
                     'sql/20_absorption_phase_b/02_tables.sql',
                     'sql/96_absorcion_ventas/00_reconciliacion.sql',
                     'sql/96_absorcion_ventas/01_contract.sql']:
            conn.execute((ROOT/path).read_text(), prepare=False)
        yield conn
        conn.rollback()


def unit(db, code='A', project='GY', kind='departamento flat', subdivision=None):
    db.execute('INSERT INTO core.dim_unidad VALUES (%s,%s,%s,%s,%s,%s)',
               (code,project,code,kind,'Disponible',subdivision))


def cycle(db, unit='A', proforma='P', project='GY', sale='2024-05-10',
          separation='2024-04-02', method='FECHA_DE_MINUTA', result='VENTA', fall=None):
    ci = sale if method=='FECHA_DE_MINUTA' else None
    db.execute('''INSERT INTO analytics.int_ciclo_comercial_unidad
      (codigo_unidad,codigo_proforma,codigo_proyecto,fecha_separacion,
       fecha_venta,fecha_de_minuta,fecha_firma_legacy,metodo_fecha_venta,resultado_ciclo,
       primera_fecha_caida,venta_source_id)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)''',
      (unit,proforma,project,separation,sale,ci,sale,method,result,fall))
    db.execute('UPDATE analytics.int_ciclo_comercial_unidad SET fecha_separacion_raw=fecha_separacion WHERE codigo_proforma=%s', (proforma,))
    db.execute("INSERT INTO raw_cygnus.procesos(codigo_proforma,codigo_unidad,nombre,fecha_inicio) VALUES (%s,%s,'Venta',%s)", (proforma,unit,sale))
    if ci:
        db.execute("INSERT INTO raw_cygnus.datos_extras(codigo,entidad,nombre,valor) VALUES (%s,'proforma','fecha_de_minuta',%s)", (proforma,ci))
    if fall:
        db.execute("INSERT INTO raw_cygnus.procesos(codigo_proforma,codigo_unidad,nombre,fecha_inicio) VALUES (%s,%s,'Anulacion',%s)", (proforma,unit,fall))
    event = 'CAIDA' if result=='CAIDA' else 'VENTA' if sale else 'SEPARACION'
    db.execute('''INSERT INTO analytics.fact_movimientos_stock
       (movement_id,source_table,source_event_key,codigo_proforma,codigo_unidad,
        codigo_proyecto,fecha_evento,tipo_evento,event_order,transition_applied)
       VALUES (%s,'test',%s,%s,%s,%s,%s,%s,1,true)''',
       (proforma,proforma,proforma,unit,project,fall or sale or separation,event))


def monthly(db, month, project='GY'):
    return db.execute('''SELECT stock_inicial,ingresos_mes,ventas_mes,stock_final
       FROM analytics.absorcion_ventas_mensual('2026-10-02')
       WHERE periodo_mes=%s AND codigo_proyecto=%s''',(month,project)).fetchone()


def test_project_start_month_and_zero_months(db):
    unit(db); unit(db,'B'); cycle(db)
    assert monthly(db,'2024-01-01')==(0,0,0,0)
    assert monthly(db,'2024-04-01')==(0,2,0,2)
    assert monthly(db,'2024-05-01')==(2,0,1,1)
    assert monthly(db,'2024-06-01')==(1,0,0,1)


def test_sales_before_2024_reduce_opening(db):
    unit(db,project='TZ'); unit(db,'B',project='TZ')
    cycle(db,project='TZ',sale='2023-09-01',separation='2023-08-01',method='LEGACY_FECHA_FIRMA_PRE_2026')
    assert monthly(db,'2024-01-01','TZ')==(1,0,0,1)


def test_failed_separation_does_not_move_stock(db):
    unit(db)
    cycle(db,proforma='FAILED',sale=None,result='CAIDA',fall='2024-04-20')
    cycle(db,proforma='SOLD',sale='2024-06-01',separation='2024-05-01')
    assert monthly(db,'2024-04-01')==(0,1,0,1)
    assert monthly(db,'2024-06-01')==(1,0,1,0)


def test_legacy_2026_is_excluded_and_visible(db):
    unit(db)
    cycle(db,sale='2026-02-01',separation='2026-01-01',method='LEGACY_FECHA_FIRMA_PRE_2026')
    assert monthly(db,'2026-02-01')==(1,0,0,1)
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='LEGACY_2026_PROHIBIDO'
    assert db.execute('SELECT count(*) FROM analytics.v_absorcion_ventas_revision').fetchone()[0]==1


def test_duplicate_sales_not_arbitrarily_selected(db):
    unit(db); cycle(db); cycle(db,proforma='P2',sale='2024-06-01')
    assert db.execute('SELECT fecha_venta,ventas_elegibles,requiere_revision FROM analytics.v_absorcion_ventas_unidad').fetchone()==(None,2,True)
    assert monthly(db,'2024-06-01')==(1,0,0,1)


def test_partial_month_and_future_sale(db):
    unit(db); unit(db,'B')
    cycle(db,sale='2026-10-02'); cycle(db,unit='B',proforma='P2',sale='2026-10-03')
    assert monthly(db,'2026-10-01')==(2,0,1,1)
    assert db.execute("SELECT fecha_corte,mes_parcial FROM analytics.absorcion_ventas_mensual('2026-10-02') WHERE periodo_mes='2026-10-01'").fetchone()==(date(2026,10,2),True)


def test_accessories_and_missing_projects(db):
    unit(db); unit(db,'PARK',kind='estacionamiento'); unit(db,'OTHER',project='UNKNOWN')
    assert db.execute('SELECT count(*) FROM analytics.v_absorcion_ventas_unidad').fetchone()[0]==1
    assert db.execute('SELECT * FROM analytics.v_absorcion_proyectos_sin_inicio').fetchone()==('UNKNOWN',1)


def test_conservation_and_idempotent_install(db):
    unit(db); cycle(db)
    db.execute((ROOT/'sql/96_absorcion_ventas/01_contract.sql').read_text(),prepare=False)
    assert db.execute('SELECT count(*) FROM analytics.absorcion_inicio_proyecto').fetchone()[0]==17
    assert db.execute("SELECT count(*) FROM analytics.absorcion_ventas_mensual('2026-10-02') WHERE stock_inicial+ingresos_mes-ventas_mes<>stock_final OR stock_final<0").fetchone()[0]==0
    assert db.execute("SELECT count(*) FROM analytics.absorcion_ventas_mensual('2026-10-02')").fetchone()[0]==34


def test_pre_project_sale_advances_start_and_preserves_original(db):
    unit(db); cycle(db,sale='2024-03-20',separation='2024-03-01')
    assert monthly(db,'2024-03-01')==(0,1,1,0)
    assert monthly(db,'2024-04-01')==(0,0,0,0)
    assert db.execute("SELECT fecha_ingreso_stock,fecha_ingreso_efectiva FROM analytics.v_absorcion_inicio_proyecto WHERE codigo_proyecto='GY'").fetchone()==(date(2024,4,1),date(2024,3,1))


def test_payment_before_separation_is_accepted_with_comment(db):
    unit(db); cycle(db,sale='2026-01-01',separation='2026-01-24')
    assert monthly(db,'2026-01-01')==(1,0,1,0)
    assert 'anterior a separación original' in db.execute('SELECT observacion FROM analytics.v_absorcion_ventas_observaciones').fetchone()[0]


@pytest.mark.parametrize('fall',['2024-05-01','2024-06-01'])
def test_cancelled_sale_removed_retrospectively(db,fall):
    unit(db); cycle(db,sale='2024-05-01',fall=fall)
    assert monthly(db,'2024-05-01')==(1,0,0,1)
    assert not db.execute('SELECT requiere_revision FROM analytics.v_absorcion_ventas_unidad').fetchone()[0]
    cycle(db,proforma='RESALE',sale='2024-07-01')
    assert monthly(db,'2024-07-01')==(1,0,1,0)


def test_sale_process_without_initial_payment_date_stays_pending(db):
    unit(db)
    cycle(db,sale=None,separation='2026-01-10',method='NO_CONFIRMADA',result='ABIERTA')
    assert monthly(db,'2026-02-01')==(1,0,0,1)
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='VENTA_SIN_FECHA_CONFIRMADA'


def test_payment_date_priority_and_project_consistency(db):
    unit(db); cycle(db)
    db.execute("UPDATE raw_cygnus.datos_extras SET valor='2024-06-01'")
    assert db.execute('SELECT fecha_venta FROM analytics.v_absorcion_ventas_unidad').fetchone()[0]==date(2024,6,1)
    db.execute("UPDATE analytics.int_ciclo_comercial_unidad SET codigo_proyecto='CP'")
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='PROYECTO_INCONSISTENTE'


def test_install_preserves_legacy_view_and_handles_appended_columns(db):
    # Emulate a live DB whose older canonical view has a different signature.
    assert db.execute('SELECT * FROM analytics.v_ciclo_comercial_reconciliado').fetchone()==(1,)
    before = db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='analytics' AND table_name='v_absorcion_ventas_reconciliado' ORDER BY ordinal_position").fetchall()
    db.execute('ALTER TABLE analytics.int_ciclo_comercial_unidad ADD COLUMN future_compatibility text')
    db.execute((ROOT/'sql/96_absorcion_ventas/00_reconciliacion.sql').read_text(),prepare=False)
    db.execute((ROOT/'sql/96_absorcion_ventas/01_contract.sql').read_text(),prepare=False)
    after = db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='analytics' AND table_name='v_absorcion_ventas_reconciliado' ORDER BY ordinal_position").fetchall()
    assert before==after
    assert db.execute('SELECT * FROM analytics.v_ciclo_comercial_reconciliado').fetchone()==(1,)


def test_recover_legacy_before_shifted_separation_without_ledger(db):
    unit(db,project='CUBA'); cycle(db,project='CUBA',sale='2019-05-01',separation='2019-04-01',method='LEGACY_FECHA_FIRMA_PRE_2026')
    db.execute("UPDATE analytics.int_ciclo_comercial_unidad SET fecha_separacion='2021-09-20',fecha_venta=NULL,fecha_firma_legacy=NULL,venta_source_id=NULL")
    db.execute('DELETE FROM analytics.fact_movimientos_stock')
    assert monthly(db,'2024-01-01','CUBA')==(0,0,0,0)
    assert 'recuperada' in db.execute('SELECT observacion FROM analytics.v_absorcion_ventas_observaciones').fetchone()[0]


def test_inactive_sale_does_not_supply_legacy_fallback(db):
    unit(db); cycle(db,method='LEGACY_FECHA_FIRMA_PRE_2026')
    db.execute("UPDATE raw_cygnus.procesos SET estado='Inactivo'")
    assert monthly(db,'2024-05-01')==(1,0,0,1)


def test_original_or_analytic_2026_boundary_blocks_fallback(db):
    unit(db); cycle(db,sale='2026-02-01',separation='2025-12-01',method='LEGACY_FECHA_FIRMA_PRE_2026')
    db.execute("UPDATE analytics.int_ciclo_comercial_unidad SET fecha_separacion='2026-01-01'")
    assert monthly(db,'2026-02-01')==(1,0,0,1)


def test_invalid_latest_payment_never_falls_back(db):
    unit(db); cycle(db)
    db.execute("INSERT INTO raw_cygnus.datos_extras(codigo,entidad,nombre,valor,fecha_actualizacion) VALUES ('P','proforma','fecha_de_minuta','bad date','2026-10-02')")
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='FECHA_PAGO_CI_INVALIDA'
    assert monthly(db,'2024-05-01')==(1,0,0,1)


def test_cancellation_before_shifted_separation_still_excludes(db):
    unit(db); cycle(db,fall='2024-06-01')
    db.execute("UPDATE analytics.int_ciclo_comercial_unidad SET fecha_separacion='2024-08-01'")
    assert monthly(db,'2024-05-01')==(1,0,0,1)


def test_business_exclusion_is_preserved(db):
    unit(db); cycle(db,proforma='2026-0002275')
    assert db.execute('SELECT count(*) FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]==0


def test_cancelled_evidence_keeps_historical_project_start(db):
    unit(db); cycle(db,sale='2024-02-01',fall='2024-03-01')
    assert monthly(db,'2024-02-01')==(0,1,0,1)
    assert monthly(db,'2024-04-01')==(1,0,0,1)


@pytest.mark.parametrize('subdivision', ['NP-B', None, '', 'NP-C'])
def test_napoles_only_enabled_subdivision_counts(db, subdivision):
    unit(db, code='ENABLED', project='NP', subdivision='NP-A')
    unit(db, code='BLOCKED', project='NP', subdivision=subdivision)
    cycle(db, unit='BLOCKED', project='NP', sale='2024-02-01')
    # Blocked evidence cannot move the project start or count as a sale.
    assert db.execute("SELECT fecha_ingreso_efectiva FROM analytics.v_absorcion_inicio_proyecto WHERE codigo_proyecto='NP'").fetchone()[0] == date(2025,8,1)
    assert monthly(db, '2025-08-01', 'NP') == (0,1,0,1)
    assert monthly(db, '2026-10-01', 'NP') == (1,0,0,1)
    assert db.execute("SELECT codigo_unidad FROM analytics.v_absorcion_ventas_unidad WHERE codigo_proyecto='NP'").fetchall() == [('ENABLED',)]
    assert db.execute("SELECT count(*) FROM analytics.v_absorcion_ventas_ciclos WHERE codigo_proyecto='NP'").fetchone()[0] == 0
    cycle(db, unit='ENABLED', proforma='VALID', project='NP', sale='2026-09-01', separation='2026-08-01')
    assert monthly(db, '2026-09-01', 'NP') == (1,0,1,0)
    assert db.execute("SELECT total_departamentos FROM analytics.absorcion_ventas_mensual('2026-10-02') WHERE codigo_proyecto='NP' AND periodo_mes='2026-10-01'").fetchone()[0] == 1
    # Reinstall is safe with dependent monthly views already present.
    db.execute((ROOT/'sql/96_absorcion_ventas/01_contract.sql').read_text(), prepare=False)
    assert monthly(db, '2026-09-01', 'NP') == (1,0,1,0)


def test_other_projects_keep_all_subdivisions(db):
    for code, subdivision in [('A','NP-B'), ('B',None), ('C','OTHER')]:
        unit(db, code=code, subdivision=subdivision)
    assert monthly(db, '2026-10-01') == (3,0,0,3)
