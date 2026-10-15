import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "13_marketing_agency_audiences_economics_lab.ipynb"
CONFIG = ROOT / "config" / "marketing_agency_channels.yml"


def _source(*, code_only: bool = False) -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload.get("cells", [])
        if not code_only or cell.get("cell_type") == "code"
    )


def test_agency_notebook_has_economic_and_causal_guardrails() -> None:
    source = _source().lower()
    for token in [
        "wilson",
        "hipótesis",
        "cohort",
        "hhi",
        "asociación",
        "causalidad",
        "grupo control",
    ]:
        assert token in source


def test_agency_notebook_uses_configured_media_and_local_mart() -> None:
    code = _source(code_only=True).lower()
    assert "marketing_agency_channels.yml" in code
    assert "analytics.marketing_audiencias" in code
    assert "analytics.marketing_audiencias_proyectos" in code
    assert "media = sorted(alias)" in code
    assert "redshift" not in code


def test_notebook_supports_optional_date_window() -> None:
    source = _source().lower()
    code = _source(code_only=True).lower()
    assert "fecha_inicio" in code
    assert "fecha_corte" in code
    assert "01/07/26" in source
    assert "15/10/26" in source
    assert "none = sin límite" in source
    assert "fecha_origen_primario" in code


def test_notebook_uses_origin_proforma_conversion_lineage() -> None:
    source = _source().lower()
    for token in [
        "proyecto_origen",
        "proyecto_proforma",
        "proyecto_conversion",
        "cambio_proyecto",
        "05_origen_conversion",
        "06_flujo_proyectos",
        "07_proyecto_detalle",
    ]:
        assert token in source


def test_internal_and_external_exports_are_separated() -> None:
    code = _source(code_only=True).lower()
    assert "10_positiva_interna" in code
    assert "11_negativa_rmkt_interna" in code
    assert "12_neutral_reciente" in code
    assert "20_positiva_exportable" in code
    assert "21_negativa_exportable" in code

    assert 'base_pos_ext = base_pos[' in code
    assert 'base_neg_ext = base_neg[' in code
    assert '["apto_entrega_externa"]' in code

    assert "display(base_pos" not in code
    assert "display(base_neg" not in code
    assert "display(base_neutral" not in code


def test_agency_config_contains_expected_initial_media() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    labels = [item["label"].lower() for item in payload["channels"]]
    aliases = {
        alias.strip().lower()
        for item in payload["channels"]
        for alias in item["match_values"]
    }
    assert labels == ["facebook", "tik tok", "instagram", "meta", "google"]
    assert {"facebook", "tik tok", "instagram", "meta", "google"}.issubset(aliases)
