from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DecisionDefinition:
    key: str
    owner: str
    entity: str
    cadence: str
    baseline: str
    outcome: str
    horizon_days: int
    priority: int
    action_space: tuple[str, ...]


class DecisionRegistry:
    def __init__(self, definitions: dict[str, DecisionDefinition], defaults: dict[str, Any] | None = None):
        self._definitions = definitions
        self.defaults = defaults or {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DecisionRegistry":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        definitions: dict[str, DecisionDefinition] = {}
        for key, item in payload.get("decisions", {}).items():
            definitions[key] = DecisionDefinition(
                key=key,
                owner=item["owner"],
                entity=item["entity"],
                cadence=item["cadence"],
                baseline=item["baseline"],
                outcome=item["outcome"],
                horizon_days=int(item["horizon_days"]),
                priority=int(item["priority"]),
                action_space=tuple(item.get("action_space", [])),
            )
        return cls(definitions, payload.get("defaults", {}))

    def get(self, key: str) -> DecisionDefinition:
        return self._definitions[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self._definitions.keys())

    def prioritized(self) -> list[DecisionDefinition]:
        return sorted(self._definitions.values(), key=lambda d: d.priority)
