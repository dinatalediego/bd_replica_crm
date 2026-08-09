from __future__ import annotations

from pathlib import Path

import yaml

from .contracts import DecisionContract


def load_decision_contracts(path: Path) -> list[DecisionContract]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("decision_systems", [])
    if not isinstance(items, list):
        raise ValueError("decision_systems debe ser una lista")
    return [DecisionContract.from_dict(item) for item in items]
