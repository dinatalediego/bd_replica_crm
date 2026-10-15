import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_validate():
    path = ROOT / "scripts" / "refresh_marketing_audiences.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_inactivity_days"
    ]
    namespace = {}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace["validate_inactivity_days"]


def test_inactivity_window_guard():
    validate = _load_validate()
    assert validate(1) == 1
    assert validate(180) == 180
    assert validate(3650) == 3650
    for bad in (0, -1, 3651):
        try:
            validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"se aceptó ventana inválida: {bad}")


def test_schema_exposes_required_provider_fields_and_privacy_gate():
    sql = (ROOT / "sql" / "115_marketing_audiences" / "01_contract.sql").read_text(
        encoding="utf-8"
    )
    for field in ('"Nombres"', '"Apellidos"', '"Telefono_Celular"', '"Correo_electronico"'):
        assert field in sql
    assert "apto_entrega_externa" in sql
    assert "marketing_consentimientos" in sql
    assert "marketing_supresiones" in sql


def test_marketing_refresh_uses_local_sources_only():
    source = (ROOT / "scripts" / "refresh_marketing_audiences.py").read_text(
        encoding="utf-8"
    )
    assert "raw_cygnus.clientes" in source
    assert "raw_cygnus.procesos" in source
    assert "raw_cygnus.proformas" in source
    assert "redshift" not in source.lower()
