from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_lab_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if "lab" not in cfg:
        raise ValueError("La configuración debe incluir la sección 'lab'.")
    return cfg
