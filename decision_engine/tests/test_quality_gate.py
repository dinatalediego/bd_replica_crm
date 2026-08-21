import pytest

from cygnus_decision_engine.cli import _separation_risk_health_is_unsafe


def healthy(**overrides):
    base = {
        "universe_candidates": 120,
        "eligible_candidates": 20,
        "candidates": 20,
        "distinct_candidates": 20,
        "duplicate_candidates": 0,
        "excluded_active_entrega_process": 0,
        "excluded_proforma_older_than_3_months": 90,
        "excluded_missing_proforma_date": 5,
        "excluded_proforma_after_observed_at": 0,
        "excluded_missing_observed_at": 0,
        "excluded_pago_ci_marker_confirmed": 5,
        "blocked_unknown_pago_ci_marker": 0,
        "excluded_positive_initial_payment_amount": 0,
        "blocked_unparseable_initial_payment_amount": 0,
        "current_with_pago_ci_marker": 0,
        "current_with_active_entrega_process": 0,
        "current_with_positive_initial_payment_amount": 0,
        "current_with_unparseable_initial_payment_amount": 0,
        "current_outside_proforma_recency_window": 0,
        "quality_blocked": 0,
        "missing_observed_at": 0,
        "core_sale_date_contract_ready": True,
        "core_abiertas_residenciales_con_pago_ci": 0,
        "core_ventas_por_pago_ci": 40,
        "core_ventas_legacy_pre_2026": 100,
        "core_ventas_post_2026_sin_pago_ci": 0,
        "core_marcadores_pago_ci_confirmados_sin_fecha": 12,
        "core_marcadores_pago_ci_desconocidos": 0,
        "core_abiertas_residenciales_con_monto_pago_ci_positivo": 0,
        "core_montos_pago_ci_positivos_sin_fecha_ni_marcador": 0,
        "core_montos_pago_ci_no_parseables": 0,
        "core_ciclos_con_evidencia_pago_ci": 40,
    }
    base.update(overrides)
    return base


def test_normal_business_exclusions_do_not_contaminate_current_candidates() -> None:
    # Old proformas, active Entrega processes, missing proforma dates, confirmed
    # payment markers and positive payment amounts are safe when explicitly
    # excluded and accounted for.
    assert _separation_risk_health_is_unsafe(healthy()) is False


def test_active_entrega_is_safe_only_when_it_is_excluded_from_scoring() -> None:
    health = healthy(universe_candidates=121, excluded_active_entrega_process=1)
    assert _separation_risk_health_is_unsafe(health) is False
    assert _separation_risk_health_is_unsafe(healthy(current_with_active_entrega_process=1)) is True


def test_positive_initial_payment_amount_is_safe_only_when_excluded() -> None:
    health = healthy(universe_candidates=121, excluded_positive_initial_payment_amount=1)
    assert _separation_risk_health_is_unsafe(health) is False
    assert _separation_risk_health_is_unsafe(
        healthy(current_with_positive_initial_payment_amount=1)
    ) is True


def test_unparseable_initial_payment_amount_blocks_decisions() -> None:
    assert _separation_risk_health_is_unsafe(
        healthy(blocked_unparseable_initial_payment_amount=1, universe_candidates=121)
    ) is True
    assert _separation_risk_health_is_unsafe(
        healthy(current_with_unparseable_initial_payment_amount=1)
    ) is True


@pytest.mark.parametrize(
    "field",
    [
        "duplicate_candidates",
        "quality_blocked",
        "missing_observed_at",
        "current_outside_proforma_recency_window",
        "excluded_proforma_after_observed_at",
        "excluded_missing_observed_at",
        "current_with_pago_ci_marker",
        "current_with_active_entrega_process",
        "current_with_positive_initial_payment_amount",
        "current_with_unparseable_initial_payment_amount",
        "blocked_unparseable_initial_payment_amount",
        "core_abiertas_residenciales_con_pago_ci",
        "core_ventas_post_2026_sin_pago_ci",
        "core_marcadores_pago_ci_desconocidos",
    ],
)
def test_hard_quality_failures_block_decisions(field: str) -> None:
    assert _separation_risk_health_is_unsafe(healthy(**{field: 1})) is True


def test_confirmed_marker_without_date_is_safe_only_when_excluded() -> None:
    assert _separation_risk_health_is_unsafe(
        healthy(core_marcadores_pago_ci_confirmados_sin_fecha=60)
    ) is False
    assert _separation_risk_health_is_unsafe(healthy(current_with_pago_ci_marker=1)) is True


def test_missing_core_sale_date_contract_blocks_decisions() -> None:
    assert _separation_risk_health_is_unsafe(healthy(core_sale_date_contract_ready=False)) is True


def test_candidate_count_must_equal_eligible_and_distinct_count() -> None:
    assert _separation_risk_health_is_unsafe(healthy(eligible_candidates=21)) is True
    assert _separation_risk_health_is_unsafe(healthy(distinct_candidates=19)) is True


def test_every_universe_row_must_land_in_exactly_one_eligibility_bucket() -> None:
    assert _separation_risk_health_is_unsafe(healthy(universe_candidates=121)) is True
