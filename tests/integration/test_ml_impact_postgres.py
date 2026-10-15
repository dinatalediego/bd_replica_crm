"""Synthetic contract test. ABSORCION_TEST_DSN must be a disposable database."""

import os
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db():
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("ABSORCION_TEST_DSN")
    if not dsn:
        pgserver = pytest.importorskip("pgserver")
        import tempfile
        dsn = pgserver.get_server(tempfile.mkdtemp(prefix="impact-test-"), cleanup_mode="delete").get_uri()
    with psycopg.connect(dsn) as conn:
        # Creating schemas (without IF NOT EXISTS) refuses a non-disposable target.
        conn.execute("CREATE SCHEMA core; CREATE SCHEMA analytics")
        conn.execute("CREATE TABLE core.dim_proyecto (codigo_proyecto text PRIMARY KEY)")
        conn.execute("""CREATE FUNCTION analytics.absorcion_ventas_mensual(date)
            RETURNS TABLE(periodo_mes date,codigo_proyecto text,stock_final bigint,unidades_revision bigint)
            LANGUAGE sql AS $$ SELECT NULL::date,NULL::text,NULL::bigint,NULL::bigint WHERE false $$""")
        sql = (ROOT / "sql/98_ml_impact/01_contract.sql").read_text(encoding="utf-8")
        conn.execute(sql, prepare=False)
        conn.execute(sql, prepare=False)  # schema sync is idempotent
        yield conn
        conn.rollback()


def add_metric(db, snapshot, code, name, block, indicator, value):
    db.execute("""INSERT INTO decision_intelligence.ml_impact_metric
        (snapshot_id,codigo_proyecto,nombre_proyecto_fuente,bloque,indicador,tipo,valor)
        VALUES (%s,%s,%s,%s,%s,'money_count',%s)""",
        (snapshot, code, name, block, indicator, value))


def test_scenarios_keep_excess_and_gap_reported_separate(db):
    snapshot = uuid4()
    db.execute("INSERT INTO core.dim_proyecto VALUES ('NP'),('TZ')")
    db.execute("""INSERT INTO decision_intelligence.ml_impact_snapshot
        (snapshot_id,as_of_date,source_name,source_sha256)
        VALUES (%s,'2026-10-04','synthetic.xlsx',%s)""", (snapshot, "a" * 64))
    for code, name, meta, placed, gap, sold, sep, stock, available, blocked in [
        ("NP", "Torre Nápoles", 48, 41, 18, 24, 17, 40, 39, 1),
        ("TZ", "Tizón y Bueno", 43, 46, 0, 45, 1, 1, 1, 0),
    ]:
        for block, indicator, value in [
            ("1. Resumen comercial", "Meta Total Departamentos", meta),
            ("1. Resumen comercial", "Valor Total Colocado", placed),
            ("1. Resumen comercial", "Gap a Meta", gap),
            ("4. Composición de ventas", "Valor Unidades Vendidas", sold),
            ("4. Composición de ventas", "Valor Unidades Separadas", sep),
            ("5. Stock Por vender", "Valor Stock Disponible", stock),
            ("5. Stock Por vender", "Valor Unidades Disponible", available),
            ("5. Stock Por vender", "Valor Unidades Bloqueadas", blocked),
        ]:
            add_metric(db, snapshot, code, name, block, indicator, value)
    project = db.execute("""SELECT gap_matematico_soles,diferencia_gap_soles,
                            impacto_potencial_soles,impacto_hacia_meta_soles
        FROM decision_intelligence.v_ml_impact_proyecto
        WHERE codigo_proyecto='NP' AND scenario_set_id='EXCEL_V1' AND scenario_code='BASE'""").fetchone()
    assert project == (Decimal(7), Decimal(11), Decimal(4), Decimal(4))
    portfolio = db.execute("""SELECT gap_matematico_soles,gap_neto_portafolio_soles,
                                   impacto_potencial_soles,impacto_hacia_meta_soles,
                                   proyectos_revision
        FROM decision_intelligence.v_ml_impact_portafolio_actual
        WHERE scenario_set_id='EXCEL_V1' AND scenario_code='BASE'""").fetchone()
    assert portfolio == (Decimal(7), Decimal(4), Decimal("4.1"), Decimal(4), 1)
    available_only = db.execute("""SELECT impacto_potencial_soles
        FROM decision_intelligence.v_ml_impact_portafolio_actual
        WHERE scenario_set_id='DISPONIBLE_V1' AND scenario_code='BASE'""").fetchone()[0]
    assert available_only == Decimal(4)
    with pytest.raises(Exception, match="inmutable"):
        db.execute("""UPDATE decision_intelligence.ml_impact_scenario
                      SET uplift_fraction=.3 WHERE scenario_set_id='EXCEL_V1'""")
