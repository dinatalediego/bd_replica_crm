from __future__ import annotations

from abc import ABC, abstractmethod

from .types import FamilyResult, LabContext


class ProbabilityFamily(ABC):
    family_id: str
    title: str
    question: str

    @abstractmethod
    def run(self, ctx: LabContext) -> FamilyResult:
        raise NotImplementedError
