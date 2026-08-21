from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _normalized_feature_sql() -> str:
    sql = (ROOT / "sql" / "02_separation_fall_risk_features.sql").read_text(
        encoding="utf-8"
    )
    return " ".join(sql.lower().split())


def test_active_entrega_is_resolved_at_proforma_unit_grain() -> None:
    sql = _normalized_feature_sql()

    assert "active_entrega as" in sql
    assert "lower(coalesce(nombre,'')) = 'entrega'" in sql
    assert "lower(coalesce(estado,'')) = 'activo'" in sql
    assert "group by codigo_proforma::text, codigo_unidad::text" in sql
    assert "ae.codigo_proforma = c.codigo_proforma" in sql
    assert "ae.codigo_unidad = c.codigo_unidad" in sql


def test_active_entrega_has_explicit_exclusion_and_safety_metrics() -> None:
    sql = _normalized_feature_sql()

    assert "excluded_active_entrega_process" in sql
    assert "current_with_active_entrega_process" in sql
    assert "active_entrega_process_must_not_be_scored" in sql
    assert "has_active_entrega_process" in sql
