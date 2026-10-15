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
    for token in ["wilson", "hipótesis", "cohort", "hhi", "asociación", "causalidad", "grupo control"]:
        assert token in source


def test_agency_notebook_uses_configured_media_and_local_mart() -> None:
    code = _source(code_only=True).lower()
    assert "marketing_agency_channels.yml" in code
    assert "analytics.marketing_audiencias" in code
    assert "media=sorted(alias)" in code
    assert "redshift" not in code


def test_activation_exports_require_external_eligibility() -> None:
    code = _source(code_only=True).lower().replace(" ", "")
    assert "analytics.v_marketing_positiva" in code
    assert "analytics.v_marketing_negativa_sin_avance" in code
    assert code.count("whereapto_entrega_externa=true") >= 2
    assert "10_base_positiva" in code
    assert "11_base_negativa" in code
    assert "display(base_pos" not in code
    assert "display(base_neg" not in code


def test_agency_config_contains_expected_initial_media() -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    labels = [item["label"].lower() for item in payload["channels"]]
    aliases = {alias.strip().lower() for item in payload["channels"] for alias in item["match_values"]}
    assert labels == ["facebook", "tik tok", "instagram", "meta", "google"]
    assert {"facebook", "tik tok", "instagram", "meta", "google"}.issubset(aliases)
