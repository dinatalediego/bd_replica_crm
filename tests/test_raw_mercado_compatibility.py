from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_powerbi_units_accepts_historical_market_unit_names():
    sql = (ROOT / "sql/init_unidades_powerbi.sql").read_text(encoding="utf-8").lower()
    assert "j->>'codigo_unidad'" in sql
    assert "j->>'nombre_unidad'" in sql
    assert "j->>'tipologia'" in sql
    assert "update raw_mercado.unidades" not in sql
    assert "trim(codigo)" not in sql


def test_multisource_contract_reads_market_rows_through_json():
    sql = (ROOT / "sql/40_unidades_multifuente/01_v_unidades_fuentes.sql").read_text(encoding="utf-8").lower()
    assert "to_jsonb(u)" in sql
    assert "j->>'codigo_unidad'" in sql
    assert "j->>'source_id'" in sql
    assert "replace(area_total_raw" in sql
    assert "u.codigo::text" not in sql


def test_market_lifecycle_consumes_canonical_compatibility_view():
    sql = (ROOT / "sql/40_unidades_multifuente/02_market_lifecycle_inferido.sql").read_text(encoding="utf-8").lower()
    assert sql.count("from core.v_unidades_fuentes") >= 2
    assert "from raw_mercado.unidades" not in sql
    assert "u.unidad_fuente_key" in sql
    assert "u.source_loaded_at" in sql
    assert "u._etl_loaded_at" not in sql
    assert "where esquema_fuente = 'raw_mercado'\n      and codigo_proyecto" in sql
