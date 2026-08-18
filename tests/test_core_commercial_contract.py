from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "init_core_commercial.sql"
SERVICE_PATH = ROOT / "src" / "replica_cygnus" / "core_commercial" / "service.py"


def test_core_sql_declares_governed_entities() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8").lower()

    assert "create schema if not exists core" in sql
    assert "core.dim_proyecto" in sql
    assert "core.dim_unidad" in sql
    assert "codigo_proyecto" in sql
    assert "references core.dim_proyecto(codigo_proyecto)" in sql


def test_core_service_contains_reconciliation_guards() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")

    assert "raw_proyectos != core_proyectos" in source
    assert "raw_unidades != core_unidades" in source
    assert '"proyectos_con_diferencia"' in source
    assert '"unidades_huerfanas"' in source
