from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    name: str
    value: Any
    source: str | None = None
    observed_at: datetime | None = None


class DecisionContext(BaseModel):
    decision_key: str
    entity_type: str
    entity_id: str
    observed_at: datetime
    features: dict[str, Any] = Field(default_factory=dict)
    quality_status: Literal["OK", "WARN", "BLOCKED"] = "OK"
    quality_reasons: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    recommendation_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_key: str
    entity_type: str
    entity_id: str
    generated_at: datetime
    action: str
    score: float | None = None
    confidence: float | None = None
    expected_value: float | None = None
    policy_version: str
    explanation: str
    evidence: list[Evidence] = Field(default_factory=list)
    status: Literal["ACTIVE", "BLOCKED", "EXPIRED"] = "ACTIVE"

    @classmethod
    def blocked(cls, context: DecisionContext, *, policy_version: str) -> "Recommendation":
        reasons = "; ".join(context.quality_reasons) or "quality gate failed"
        return cls(
            decision_key=context.decision_key,
            entity_type=context.entity_type,
            entity_id=context.entity_id,
            generated_at=context.observed_at,
            action="do_not_decide",
            policy_version=policy_version,
            explanation=f"Decision blocked: {reasons}",
            status="BLOCKED",
        )
