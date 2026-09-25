from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_schema_sync_registers_clientes_calidad_component() -> None:
    code = (ROOT / "scripts" / "schema_sync.py").read_text(encoding="utf-8").lower()

    assert 'name="clientes_calidad"' in code
    assert "sql/90_clientes_calidad/01_clientes_calidad.sql" in code
    assert "staging.clientes_calidad" in code
    assert "staging.refresh_clientes_calidad()" in code
    assert "staging.v_clientes_calidad_health" in code


def test_clientes_calidad_sql_preserves_phone_priority_contract() -> None:
    sql = (ROOT / "sql" / "90_clientes_calidad" / "01_clientes_calidad.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "when src ? 'celulares' then src ->> 'celulares'" in sql
    assert "when src ? 'celular' then src ->> 'celular'" in sql
    assert "when e.valor_celular is not null then e.valor_celular" in sql
    assert "else e.telefono" in sql
    assert "when e.valor_celular is not null then e.columna_celular" in sql
    assert "when e.telefono is not null then 'telefono'" in sql


def test_clientes_calidad_sql_keeps_foreign_phone_and_dni_review_states() -> None:
    sql = (ROOT / "sql" / "90_clientes_calidad" / "01_clientes_calidad.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "'celular extranjero'" in sql
    assert "'revisar formato'" in sql
    assert "when s.dq_documento_limpio is null then 'revisar dni'" in sql
    assert "length(p.dq_documento_limpio) between 8 and 12" in sql


def test_clientes_calidad_refresh_has_row_count_gate() -> None:
    code = (ROOT / "scripts" / "refresh_clientes_calidad.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "call staging.refresh_clientes_calidad()" in code
    assert "staging.v_clientes_calidad_health" in code
    assert 'health["filas_raw"]' in code
    assert 'health["filas_staging"]' in code
