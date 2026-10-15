import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "12_marketing_audiences_economics_lab.ipynb"


def _source(*, code_only: bool = False) -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload.get("cells", [])
        if not code_only or cell.get("cell_type") == "code"
    )


def test_notebook_is_single_privacy_safe_economic_lab() -> None:
    source = _source().lower()
    code = _source(code_only=True).lower()
    assert "analytics.marketing_audiencias" in source
    assert "intervalos de confianza" in source
    assert "hipótesis" in source
    assert "matriz" in source
    assert "cohorte" in source
    assert "persona_key" not in code
    assert "telefono_celular" not in code
    assert "correo_electronico" not in code


def test_notebook_distinguishes_association_from_causality() -> None:
    source = _source().lower()
    assert "asociación" in source
    assert "causalidad" in source
    assert "grupo control" in source

