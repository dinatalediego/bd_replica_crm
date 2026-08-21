from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE_SQL = ROOT / "sql" / "02_separation_fall_risk_features.sql"
RUNTIME_SQL = ROOT / "sql" / "01_separation_fall_risk_runtime.sql"


def test_feature_contract_uses_certified_lifecycle_and_active_separation() -> None:
    sql = FEATURE_SQL.read_text(encoding="utf-8")
    assert "core.fact_ciclo_comercial_unidad" in sql
    assert "resultado_ciclo = 'ABIERTA'" in sql
    assert "s.estado = 'Activo'" in sql
    assert "separation_id" in sql
    assert "analytics_refreshed_at AS observed_at" in sql
    assert "quality_status" in sql
    assert "quality_reasons" in sql


def test_proforma_recency_contract_is_conservative_and_auditable() -> None:
    sql = FEATURE_SQL.read_text(encoding="utf-8")
    assert "raw_cygnus.proforma_unidad" in sql
    assert "MIN(fecha_creacion) AS proforma_first_seen_at" in sql
    assert "interval '3 months'" in sql
    assert "features.v_separation_fall_risk_candidate_universe" in sql
    assert "EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS" in sql
    assert "BLOCKED_MISSING_PROFORMA_DATE" in sql
    assert "BLOCKED_PROFORMA_AFTER_OBSERVED_AT" in sql
    assert "WHERE u.eligibility_status = 'ELIGIBLE'" in sql
    assert "current_outside_proforma_recency_window" in sql
    assert "separation-fall-risk-current-v0.5.0" in sql


def test_three_month_boundary_is_inclusive() -> None:
    sql = FEATURE_SQL.read_text(encoding="utf-8")
    # Older-than uses strict <, therefore exactly observed_at - 3 months remains eligible.
    assert "proforma_first_seen_at < c.analytics_refreshed_at - interval '3 months'" in sql
    assert "proforma_first_seen_at < observed_at - interval '3 months'" in sql


def test_feature_limitations_are_explicit_not_hidden() -> None:
    sql = FEATURE_SQL.read_text(encoding="utf-8")
    assert "INTERACTION_COUNT_14D_BINARY_PROXY" in sql
    assert "ADMIN_BLOCK_SIGNAL_NOT_CERTIFIED" in sql
    assert "NULL::boolean AS has_pending_admin_block" in sql
    assert "features.v_separation_fall_risk_health" in sql


def test_worklist_exposes_operational_and_eligibility_evidence() -> None:
    sql = RUNTIME_SQL.read_text(encoding="utf-8")
    for field in (
        "codigo_proforma",
        "codigo_unidad",
        "codigo_proyecto",
        "documento_cliente",
        "asesor",
        "proforma_first_seen_at",
        "proforma_age_days",
        "eligibility_rule",
        "eligibility_window_months",
        "days_since_separation",
        "days_since_last_interaction",
    ):
        assert field in sql
