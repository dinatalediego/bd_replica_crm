from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pricing_projection_is_versioned_in_medallio() -> None:
    schema_sync = (ROOT / "scripts" / "schema_sync.py").read_text(encoding="utf-8").lower()
    assert 'name="pricing_projection"' in schema_sync
    assert "analytics.fact_proyeccion_pricing" in schema_sync
    assert "pricing.refresh_fact_proyeccion_pricing()" in schema_sync


def test_pricing_projection_preserves_business_semantics() -> None:
    sql = (ROOT / "sql" / "60_pricing_projection" / "02_fact_refresh.sql").read_text(encoding="utf-8").lower()
    assert "least(v_stock_ini, v_ventas_teoricas)" in sql
    assert "v_mes >= h.mes_hito" in sql
    assert "v_pct_vendido >= h.pct_vendido_objetivo" in sql
    assert "v_precio_m2 := b.precio_m2_base + v_aumento" in sql
    assert "flag_hito_4_activado" in sql


def test_pricing_projection_refresh_is_in_master_pipeline() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8").lower()
    pricing_pos = code.index('"07_pricing_projection"')
    matview_pos = code.index('"08_materialized_views"')
    observe_pos = code.index('"99_observability"')
    assert pricing_pos < matview_pos < observe_pos


def test_powerbi_pricing_queries_are_thin_connectors() -> None:
    expected = {
        "Base_Proyeccion_Tipologia.m": "v_base_proyeccion_tipologia",
        "Supuestos_Absorcion.m": "v_supuestos_absorcion",
        "Hitos_Pricing.m": "v_hitos_pricing",
        "Fact_Proyeccion_Pricing.m": "fact_proyeccion_pricing",
    }
    for filename, relation in expected.items():
        content = (ROOT / "powerbi" / "M" / filename).read_text(encoding="utf-8")
        assert "PostgreSQL.Database" in content
        assert relation in content
        assert "List.Generate" not in content
