from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent


def _sql() -> str:
    text = (ENGINE_ROOT / "sql" / "02_separation_fall_risk_features.sql").read_text(encoding="utf-8")
    return " ".join(text.lower().split())


def test_positive_initial_payment_amount_is_explicit_exclusion() -> None:
    sql = _sql()
    assert "excluded_positive_initial_payment_amount" in sql
    assert "monto_pago_ci_positivo" in sql
    assert "positive_initial_payment_amount_must_not_be_scored" in sql


def test_unparseable_initial_payment_amount_is_blocked() -> None:
    sql = _sql()
    assert "blocked_unparseable_initial_payment_amount" in sql
    assert "monto_pago_ci_parse_error" in sql
    assert "unparseable_initial_payment_amount" in sql


def test_business_coalesce_is_governed_in_core() -> None:
    core_sql = (REPO_ROOT / "sql" / "init_core_commercial_lifecycle.sql").read_text(encoding="utf-8")
    normalized = " ".join(core_sql.lower().split())
    assert "monto_pagado_cuota_inicial" in normalized
    assert "monto_total_pagado" in normalized
    assert "monto_pagado_de_cuota_inicial" in normalized
    assert "monto_pago_ci_positivo" in normalized
