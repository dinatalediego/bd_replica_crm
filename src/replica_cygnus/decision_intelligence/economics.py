from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class EconomicPolicy:
    """Parámetros económicos usados para convertir probabilidad y efecto causal en valor."""

    value_if_success: float
    loss_if_failure: float = 0.0
    action_cost: float = 0.0
    treatment_effect: float = 0.0
    opportunity_cost: float = 0.0

    def validate(self) -> None:
        if self.value_if_success < 0:
            raise ValueError("value_if_success no puede ser negativo")
        if self.loss_if_failure < 0 or self.action_cost < 0 or self.opportunity_cost < 0:
            raise ValueError("costos y pérdidas deben expresarse como magnitudes no negativas")
        if not -1.0 <= self.treatment_effect <= 1.0:
            raise ValueError("treatment_effect debe estar entre -1 y 1")


def economic_value(
    probability_success: float,
    policy: EconomicPolicy,
    treatment_effect: float | None = None,
) -> dict[str, float]:
    """Valor esperado de no actuar vs actuar.

    `treatment_effect` es el efecto causal incremental esperado en probabilidad
    para la entidad (CATE/uplift). Si se omite, usa el efecto promedio de policy.
    """
    effect = policy.treatment_effect if treatment_effect is None else float(treatment_effect)
    effective_policy = replace(policy, treatment_effect=effect)
    effective_policy.validate()

    p = min(max(float(probability_success), 0.0), 1.0)
    p_action = min(max(p + effect, 0.0), 1.0)
    base = p * policy.value_if_success - (1.0 - p) * policy.loss_if_failure
    action_before_cost = (
        p_action * policy.value_if_success - (1.0 - p_action) * policy.loss_if_failure
    )
    action_after_cost = action_before_cost - policy.action_cost - policy.opportunity_cost
    incremental_net = action_after_cost - base
    return {
        "probability_success": p,
        "probability_with_action": p_action,
        "treatment_effect": effect,
        "expected_value_no_action": base,
        "expected_incremental_value": incremental_net,
        "expected_value_with_action": action_after_cost,
    }
