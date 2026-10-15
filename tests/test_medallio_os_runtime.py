from __future__ import annotations

import json
from pathlib import Path

import pytest

from replica_cygnus.medallio_os import runtime


def test_ensure_inside_repo_accepts_internal_path(tmp_path: Path) -> None:
    internal = tmp_path / "notebooks" / "lab.ipynb"
    internal.parent.mkdir()
    internal.write_text("{}", encoding="utf-8")
    assert runtime.ensure_inside_repo(tmp_path, internal) == internal.resolve()


def test_ensure_inside_repo_rejects_external_path(tmp_path: Path) -> None:
    external = tmp_path.parent / "outside.ipynb"
    with pytest.raises(ValueError):
        runtime.ensure_inside_repo(tmp_path, external)


def test_discover_notebooks_ignores_virtualenv_and_checkpoints(tmp_path: Path) -> None:
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "notebooks" / "a.ipynb").write_text("{}", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "hidden.ipynb").write_text("{}", encoding="utf-8")
    (tmp_path / ".ipynb_checkpoints").mkdir()
    (tmp_path / ".ipynb_checkpoints" / "b.ipynb").write_text("{}", encoding="utf-8")

    assert runtime.discover_notebooks(tmp_path) == [Path("notebooks/a.ipynb")]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("forecast_monthly.ipynb", "Forecasting"),
        ("03_causal_inference_lab.ipynb", "Econometría"),
        ("09_model_explainability_lab.ipynb", "Machine Learning"),
        ("00_command_center.ipynb", "Decision Intelligence"),
        ("stock_absorcion.ipynb", "Pricing / Stock"),
    ],
)
def test_classify_notebook(name: str, expected: str) -> None:
    assert runtime.classify_notebook(Path(name)) == expected


def test_discover_kernels_parses_jupyter_json(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "kernelspecs": {
            "medallio_dw": {"resource_dir": "C:/kernels/medallio_dw"},
            "python3": {"resource_dir": "C:/kernels/python3"},
        }
    }

    monkeypatch.setattr(
        runtime,
        "_run",
        lambda *args, **kwargs: runtime.CommandResult(
            command=("python",),
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
            started_at="x",
            finished_at="y",
        ),
    )

    kernels = runtime.discover_kernels(tmp_path)
    assert kernels["medallio_dw"] == "C:/kernels/medallio_dw"
    assert set(kernels) == {"medallio_dw", "python3"}
