from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .contracts import DecisionContext, Recommendation
from .rules import separation_fall_risk_baseline


@dataclass(frozen=True)
class SeparationCandidate:
    separation_id: str
    observed_at: datetime
    features: dict[str, Any]
    quality_status: str = "OK"
    quality_reasons: tuple[str, ...] = ()

    def to_context(self) -> DecisionContext:
        return DecisionContext(
            decision_key="separation_fall_risk",
            entity_type="separation",
            entity_id=self.separation_id,
            observed_at=self.observed_at,
            features=self.features,
            quality_status=self.quality_status,
            quality_reasons=list(self.quality_reasons),
        )


def score_separation(candidate: SeparationCandidate) -> Recommendation:
    return separation_fall_risk_baseline(candidate.to_context())


def score_candidates(candidates: Iterable[SeparationCandidate]) -> list[Recommendation]:
    recommendations = [score_separation(candidate) for candidate in candidates]
    return sorted(
        recommendations,
        key=lambda item: (
            item.status != "ACTIVE",
            -(item.score or 0.0),
            item.entity_id,
        ),
    )
