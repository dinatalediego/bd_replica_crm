from __future__ import annotations

from .base import ProbabilityFamily
from .families import (
    BayesianConversionFamily,
    ConversionBinomialFamily,
    LatentSegmentsFamily,
    PredictiveProbabilityFamily,
    TimeToEventFamily,
)

FAMILY_REGISTRY: dict[str, type[ProbabilityFamily]] = {
    cls.family_id: cls
    for cls in [
        ConversionBinomialFamily,
        BayesianConversionFamily,
        TimeToEventFamily,
        PredictiveProbabilityFamily,
        LatentSegmentsFamily,
    ]
}


def build_families(ids: list[str]) -> list[ProbabilityFamily]:
    missing = [family_id for family_id in ids if family_id not in FAMILY_REGISTRY]
    if missing:
        raise KeyError(f"Familias no registradas: {missing}")
    return [FAMILY_REGISTRY[family_id]() for family_id in ids]
