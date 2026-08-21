from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "12_horizon_training_set.sql"


def _sql() -> str:
    return " ".join(SQL.read_text(encoding="utf-8").lower().split())


def test_horizon_target_is_fixed_30_days_and_includes_open_lifecycles() -> None:
    sql = _sql()
    assert "horizon_end_at" in sql
    assert "+ 30" in sql
    assert "censored_open" in sql
    assert "target_fall_within_30d" in sql


def test_horizon_target_handles_censoring_and_transfer_competing_events() -> None:
    sql = _sql()
    assert "censored_incomplete_30d_followup" in sql
    assert "excluded_transfer_competing_event_within_30d" in sql
    assert "observed_through" in sql


def test_horizon_target_never_uses_undated_payment_evidence_as_known_time() -> None:
    sql = _sql()
    assert "excluded_undated_payment_evidence_timing_ambiguous" in sql
    assert "e.fecha_pago_ci is null" in sql
    assert "e.evidencia_pago_ci_confirmada" in sql


def test_horizon_target_preserves_live_eligibility_safety() -> None:
    sql = _sql()
    assert "interval '3 months'" in sql
    assert "excluded_entrega_already_started_at_snapshot" in sql
    assert "excluded_dated_payment_already_known_at_snapshot" in sql
    assert "proforma_first_seen_at" in sql


def test_horizon_contract_marks_label_measurement_regime_and_grouped_oot_evaluation() -> None:
    sql = _sql()
    assert "post_2026_payment_date_regime" in sql
    assert "pre_2026_legacy_compatibility_regime" in sql
    assert "group_by_separation_id_out_of_time_and_horizon_censoring_required" in sql
    assert "v_separation_fall_training_30d_regime_profile" in sql


def test_horizon_training_features_exclude_post_outcome_reason_text() -> None:
    sql = _sql()
    assert "motivo_caida_segun_asesor" not in sql
    assert "cambio_de_departamento" not in sql
    assert "depa_del_cambio" not in sql
    assert "false::boolean as interaction_features_certified" in sql
