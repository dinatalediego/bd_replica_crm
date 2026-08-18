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


def _int_feature(candidate: SeparationCandidate, name: str) -> int:
    value = candidate.features.get(name)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def score_candidates(candidates: Iterable[SeparationCandidate]) -> list[Recommendation]:
    """Score and rank candidates deterministically for an operational worklist.

    Score remains the primary ranking signal. For equal baseline scores, older
    separations and longer contact gaps are prioritized before falling back to
    the stable entity id. This avoids an arbitrary lexicographic ordering when
    many candidates share the same coarse baseline score.
    """
    scored = [
        (score_separation(candidate), candidate)
        for candidate in candidates
    ]

    ranked = sorted(
        scored,
        key=lambda pair: (
            pair[0].status != "ACTIVE",
            -(pair[0].score or 0.0),
            -_int_feature(pair[1], "days_since_separation"),
            -_int_feature(pair[1], "days_since_last_interaction"),
            _int_feature(pair[1], "interaction_count_14d"),
            pair[0].entity_id,
        ),
    )
    return [recommendation for recommendation, _candidate in ranked]
