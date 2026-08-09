from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .economics import EconomicPolicy, economic_value


@dataclass(frozen=True)
class ScoredDecision:
    entity_id: str
    probability: float
    treatment_effect: float
    expected_value_no_action: float
    expected_incremental_value: float
    expected_value_with_action: float
    recommended_action: str
    priority_rank: int


class DecisionEngine:
    """Motor auditable para priorizar acciones por valor económico incremental esperado.

    Cada fila puede traer un CATE/uplift específico. Ese es el puente explícito
    entre causalidad y decisión económica.
    """

    def __init__(
        self,
        action_name: str,
        policy: EconomicPolicy,
        min_incremental_value: float = 0.0,
        max_actions: int | None = None,
    ) -> None:
        if not action_name.strip():
            raise ValueError("action_name no puede estar vacío")
        if max_actions is not None and max_actions <= 0:
            raise ValueError("max_actions debe ser positivo")
        self.action_name = action_name
        self.policy = policy
        self.min_incremental_value = float(min_incremental_value)
        self.max_actions = max_actions

    def rank(self, rows: Iterable[tuple[str, float] | tuple[str, float, float]]) -> list[ScoredDecision]:
        provisional: list[dict] = []
        for row in rows:
            if len(row) == 2:
                entity_id, probability = row
                effect = self.policy.treatment_effect
            elif len(row) == 3:
                entity_id, probability, effect = row
            else:
                raise ValueError("Cada fila debe ser (entity_id, probability[, treatment_effect])")
            values = economic_value(probability, self.policy, treatment_effect=effect)
            provisional.append({"entity_id": str(entity_id), **values})

        provisional.sort(
            key=lambda x: (x["expected_incremental_value"], x["expected_value_with_action"]),
            reverse=True,
        )
        results: list[ScoredDecision] = []
        acted = 0
        for rank, item in enumerate(provisional, start=1):
            eligible = item["expected_incremental_value"] >= self.min_incremental_value
            within_capacity = self.max_actions is None or acted < self.max_actions
            should_act = eligible and within_capacity
            if should_act:
                acted += 1
            results.append(
                ScoredDecision(
                    entity_id=item["entity_id"],
                    probability=item["probability_success"],
                    treatment_effect=item["treatment_effect"],
                    expected_value_no_action=item["expected_value_no_action"],
                    expected_incremental_value=item["expected_incremental_value"],
                    expected_value_with_action=item["expected_value_with_action"],
                    recommended_action=self.action_name if should_act else "NO_ACTUAR",
                    priority_rank=rank,
                )
            )
        return results
