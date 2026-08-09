from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class DecisionContract:
    """Contrato mínimo que convierte un caso analítico en un sistema de decisión."""

    name: str
    objective: str
    decision_unit: str
    decision_owner: str
    available_actions: tuple[str, ...]
    target: str
    prediction_horizon_days: int
    causal_estimand: str
    primary_value_metric: str
    feedback_outcome: str
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        text_fields = {
            "name": self.name,
            "objective": self.objective,
            "decision_unit": self.decision_unit,
            "decision_owner": self.decision_owner,
            "target": self.target,
            "causal_estimand": self.causal_estimand,
            "primary_value_metric": self.primary_value_metric,
            "feedback_outcome": self.feedback_outcome,
        }
        empty = [key for key, value in text_fields.items() if not str(value).strip()]
        if empty:
            raise ValueError(f"Campos obligatorios vacíos: {', '.join(empty)}")
        if not self.available_actions:
            raise ValueError("available_actions debe contener al menos una acción")
        if self.prediction_horizon_days <= 0:
            raise ValueError("prediction_horizon_days debe ser mayor que cero")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DecisionContract":
        obj = cls(
            name=str(raw["name"]),
            objective=str(raw["objective"]),
            decision_unit=str(raw["decision_unit"]),
            decision_owner=str(raw["decision_owner"]),
            available_actions=tuple(str(x) for x in raw.get("available_actions", [])),
            target=str(raw["target"]),
            prediction_horizon_days=int(raw["prediction_horizon_days"]),
            causal_estimand=str(raw["causal_estimand"]),
            primary_value_metric=str(raw["primary_value_metric"]),
            feedback_outcome=str(raw["feedback_outcome"]),
            constraints=dict(raw.get("constraints", {})),
        )
        obj.validate()
        return obj
