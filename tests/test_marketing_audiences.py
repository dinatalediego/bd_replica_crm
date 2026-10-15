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
    assert "v_marketing_neutral_reciente" in sql


def test_schema_exposes_project_lineage():
    sql = (ROOT / "sql" / "115_marketing_audiences" / "01_contract.sql").read_text(
        encoding="utf-8"
    ).lower()

    for field in (
        "codigo_proyecto_origen",
        "proyecto_origen",
        "codigo_proyecto_proforma",
        "proyecto_proforma",
        "codigo_proyecto_conversion",
        "proyecto_conversion",
        "fuente_proyecto",
        "cambio_proyecto",
        "fecha_origen_primario",
    ):
        assert field in sql

    assert "analytics.marketing_audiencias_proyectos" in sql
    assert "origen > conversion > proforma > cliente" in sql


def test_marketing_refresh_uses_local_project_sources_only():
    source = (ROOT / "scripts" / "refresh_marketing_audiences.py").read_text(
        encoding="utf-8"
    ).lower()

    for relation in (
        "raw_cygnus.clientes",
        "raw_cygnus.clientes_proyectos",
        "raw_cygnus.procesos",
        "raw_cygnus.proformas",
        "raw_cygnus.proyectos",
        "staging.clientes_calidad",
    ):
        assert relation in source

    assert "redshift" not in source
    assert "medio_captacion_origen" in source
    assert "codigo_proyecto_origen" in source
    assert "codigo_proyecto_conversion" in source
    assert "build_projects_next_sql" in source


def test_project_resolution_prioritizes_origin():
    source = (ROOT / "scripts" / "refresh_marketing_audiences.py").read_text(
        encoding="utf-8"
    ).lower().replace("\n", " ")

    assert "coalesce(op.proyecto_origen, cp.proyecto_conversion, pp.proyecto_proforma, r.dq_proyecto)" in source
    assert "when op.proyecto_origen is not null then 'origen'" in source
