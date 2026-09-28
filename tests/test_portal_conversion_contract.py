from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_schema_contract_contains_required_assets() -> None:
    sql = (ROOT / "sql" / "95_portal_conversion" / "01_contract.sql").read_text(encoding="utf-8").lower()
    assert "staging.portal_leads_base" in sql
    assert "staging.portal_compradores_base" in sql
    assert "analytics.portal_lead_match" in sql
    assert "analytics.v_portal_conversion_medio_total" in sql
    assert "analytics.v_portal_conversion_health" in sql


def test_dw_refresh_runs_portal_conversion_after_client_quality() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8").lower()
    dq = code.index("02b_clientes_calidad_refresh")
    portal = code.index("02c_portal_conversion_refresh")
    assert dq < portal
    assert "refresh_portal_conversion.py" in code


def test_schema_sync_registers_portal_component() -> None:
    code = (ROOT / "scripts" / "schema_sync.py").read_text(encoding="utf-8").lower()
    assert 'name="portal_conversion"' in code
    assert "sql/95_portal_conversion/01_contract.sql" in code
