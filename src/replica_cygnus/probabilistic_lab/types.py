from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(slots=True)
class LabContext:
    data: pd.DataFrame
    output_dir: Path
    random_state: int
    config: dict[str, Any]


@dataclass(slots=True)
class FamilyResult:
    family_id: str
    title: str
    question: str
    theory: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    figures: list[Path] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def jsonable(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "title": self.title,
            "question": self.question,
            "theory": self.theory,
            "metrics": self.metrics,
            "insights": self.insights,
            "limitations": self.limitations,
            "figures": [str(p) for p in self.figures],
            "artifacts": self.artifacts,
        }
