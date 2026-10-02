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
        conn.execute('CREATE SCHEMA analytics; CREATE SCHEMA core; CREATE SCHEMA observability')
        conn.execute('''CREATE TABLE core.dim_unidad (
            codigo_unidad text PRIMARY KEY, codigo_proyecto text, nombre_unidad text,
            tipo_unidad text, estado_comercial text)''')
        conn.execute('CREATE VIEW analytics.v_ciclo_comercial_reconciliado AS SELECT 1 AS legacy_column')
        for path in ['sql/20_absorption_phase_b/02_tables.sql',
                     'sql/96_absorcion_ventas/00_reconciliacion.sql',
                     'sql/96_absorcion_ventas/01_contract.sql']:
            conn.execute((ROOT/path).read_text(), prepare=False)
        yield conn
        conn.rollback()


def unit(db, code='A', project='GY', kind='departamento flat'):
    db.execute('INSERT INTO core.dim_unidad VALUES (%s,%s,%s,%s,%s)',
               (code,project,code,kind,'Disponible'))


def cycle(db, unit='A', proforma='P', project='GY', sale='2024-05-10',
          separation='2024-04-02', method='FECHA_DE_MINUTA', result='VENTA', fall=None):
    ci = sale if method=='FECHA_DE_MINUTA' else None
    db.execute('''INSERT INTO analytics.int_ciclo_comercial_unidad
      (codigo_unidad,codigo_proforma,codigo_proyecto,fecha_separacion,
       fecha_venta,fecha_de_minuta,fecha_firma_legacy,metodo_fecha_venta,resultado_ciclo,
       primera_fecha_caida,venta_source_id)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)''',
      (unit,proforma,project,separation,sale,ci,sale,method,result,fall))
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


@pytest.mark.parametrize('sale,separation,fall',[
    ('2024-03-20','2024-03-01',None), # before project intake
    ('2024-05-01','2024-05-02',None), # before separation
    ('2024-05-01','2024-04-02','2024-05-01'), # sale/fall ambiguity
])
def test_invalid_or_ambiguous_sale_is_not_counted(db,sale,separation,fall):
    unit(db); cycle(db,sale=sale,separation=separation,fall=fall)
    assert monthly(db,'2024-05-01')==(1,0,0,1)
    assert db.execute('SELECT requiere_revision FROM analytics.v_absorcion_ventas_unidad').fetchone()[0]


def test_sale_process_without_initial_payment_date_stays_pending(db):
    unit(db)
    cycle(db,sale=None,separation='2026-01-10',method='NO_CONFIRMADA',result='ABIERTA')
    assert monthly(db,'2026-02-01')==(1,0,0,1)
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='VENTA_SIN_FECHA_CONFIRMADA'


def test_payment_date_priority_and_project_consistency(db):
    unit(db); cycle(db)
    db.execute("UPDATE analytics.int_ciclo_comercial_unidad SET fecha_de_minuta='2024-06-01'")
    assert db.execute('SELECT calidad_ciclo FROM analytics.v_absorcion_ventas_ciclos').fetchone()[0]=='PAGO_CI_NO_PRIORIZADO'
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
