from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .economics import EconomicPolicy, economic_value


_ALLOWED_STAGES = {"EXPECTED", "APPROVED", "REALIZED", "COUNTERFACTUAL"}
_ALLOWED_TYPES = {"REVENUE", "MARGIN", "COST_SAVING", "RISK_AVOIDED", "OPPORTUNITY", "OTHER"}


@dataclass(frozen=True)
class EconomicValueEntry:
    """Canonical application model for a row in economic_value_ledger.

    `comparison_value` is already net of the action/opportunity costs used by the
    valuation method. Costs are retained separately for auditability and must not
    be subtracted a second time.
    """

    decision_id: str
    value_name: str
    value_stage: str
    value_type: str
    currency: str
    baseline_value: float
    comparison_value: float
    direct_cost: float
    opportunity_cost: float
    net_incremental_value: float
    probability: float | None = None
    confidence_pct: float | None = None
    horizon_days: int | None = None
    valuation_basis: str = "NET_AFTER_COSTS"
    calculation_method: str = "EXPECTED_VALUE"
    formula_version: str = "v1"

    def validate(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id no puede estar vacío")
        if not self.value_name.strip():
            raise ValueError("value_name no puede estar vacío")
        if self.value_stage not in _ALLOWED_STAGES:
            raise ValueError(f"value_stage inválido: {self.value_stage}")
        if self.value_type not in _ALLOWED_TYPES:
            raise ValueError(f"value_type inválido: {self.value_type}")
        if len(self.currency) != 3 or self.currency.upper() != self.currency or not self.currency.isalpha():
            raise ValueError("currency debe ser un código ISO de 3 letras en mayúsculas")
        if self.direct_cost < 0 or self.opportunity_cost < 0:
            raise ValueError("los costos deben ser no negativos")
        if self.probability is not None and not 0 <= self.probability <= 1:
            raise ValueError("probability debe estar entre 0 y 1")
        if self.confidence_pct is not None and not 0 <= self.confidence_pct <= 100:
            raise ValueError("confidence_pct debe estar entre 0 y 100")
        if self.horizon_days is not None and self.horizon_days < 0:
            raise ValueError("horizon_days debe ser no negativo")

    @property
    def confidence_adjusted_value(self) -> float:
        confidence = 100.0 if self.confidence_pct is None else self.confidence_pct
        return self.net_incremental_value * confidence / 100.0

    def as_db_params(self) -> dict[str, Any]:
        self.validate()
        return {
            "decision_id": self.decision_id,
            "value_name": self.value_name,
            "value_stage": self.value_stage,
            "value_type": self.value_type,
            "currency": self.currency,
            "baseline_value": self.baseline_value,
            "comparison_value": self.comparison_value,
            "direct_cost": self.direct_cost,
            "opportunity_cost": self.opportunity_cost,
            "net_incremental_value": self.net_incremental_value,
            "probability": self.probability,
            "confidence_pct": self.confidence_pct,
            "horizon_days": self.horizon_days,
            "valuation_basis": self.valuation_basis,
            "calculation_method": self.calculation_method,
            "formula_version": self.formula_version,
        }


def expected_economic_value_entry(
    *,
    decision_id: str,
    value_name: str,
    probability_success: float,
    policy: EconomicPolicy,
    treatment_effect: float | None = None,
    confidence_pct: float | None = None,
    horizon_days: int | None = None,
    value_type: str = "REVENUE",
    currency: str = "PEN",
    formula_version: str = "v1",
) -> EconomicValueEntry:
    """Build an auditable EXPECTED economic-value object from the current engine."""

    values = economic_value(
        probability_success=probability_success,
        policy=policy,
        treatment_effect=treatment_effect,
    )
    entry = EconomicValueEntry(
        decision_id=decision_id,
        value_name=value_name,
        value_stage="EXPECTED",
        value_type=value_type,
        currency=currency,
        baseline_value=values["expected_value_no_action"],
        comparison_value=values["expected_value_with_action"],
        direct_cost=policy.action_cost,
        opportunity_cost=policy.opportunity_cost,
        net_incremental_value=values["expected_incremental_value"],
        probability=values["probability_success"],
        confidence_pct=confidence_pct,
        horizon_days=horizon_days,
        valuation_basis="NET_AFTER_COSTS",
        calculation_method="EXPECTED_VALUE_WITH_CAUSAL_UPLIFT",
        formula_version=formula_version,
    )
    entry.validate()
    return entry
