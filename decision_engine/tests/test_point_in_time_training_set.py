from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "10_point_in_time_training_set.sql"


def _sql() -> str:
    return " ".join(SQL.read_text(encoding="utf-8").lower().split())


def test_training_set_uses_historical_landmarks_and_requires_open_state_at_snapshot() -> None:
    sql = _sql()
    assert "values (0::integer), (7::integer), (14::integer), (21::integer)" in sql
    assert "e.outcome_at::date <= e.snapshot_at" in sql
    assert "excluded_outcome_already_known_at_snapshot" in sql


def test_training_set_reproduces_live_eligibility_safety() -> None:
    sql = _sql()
    assert "interval '3 months'" in sql
    assert "excluded_entrega_already_started_at_snapshot" in sql
    assert "excluded_dated_payment_already_known_at_snapshot" in sql
    assert "raw_cygnus.proforma_unidad" in sql
    assert "raw_cygnus.procesos" in sql


def test_training_set_has_no_post_outcome_reason_features() -> None:
    sql = _sql()
    assert "motivo_caida_segun_asesor" not in sql
    assert "cambio_de_departamento" not in sql
    assert "depa_del_cambio" not in sql
    assert "structural_temporal_only_v1" in sql


def test_training_set_requires_grouped_out_of_time_evaluation_and_balances_lifecycles() -> None:
    sql = _sql()
    assert "group_split_by_separation_id_and_out_of_time_required" in sql
    assert "count(*) over (partition by separation_id)" in sql
    assert "lifecycle_balancing_weight" in sql


def test_interaction_features_remain_uncertified_until_historical_contract_exists() -> None:
    sql = _sql()
    assert "false::boolean as interaction_features_certified" in sql
    assert "rows_with_certified_interaction_features" in sql


def test_rerun_tears_down_known_downstream_views_before_point_in_time_views() -> None:
    sql = _sql()

    downstream = [
        "drop view if exists features.v_separation_fall_training_30d_regime_profile",
        "drop view if exists features.v_separation_fall_training_30d_health",
        "drop view if exists features.separation_fall_training_30d",
        "drop view if exists features.v_separation_fall_training_30d_audit",
        "drop view if exists features.v_separation_fall_training_landmark_profile",
        "drop view if exists features.v_separation_fall_training_period_profile",
        "drop view if exists features.v_separation_fall_training_readiness",
    ]
    base_drop = "drop view if exists features.separation_fall_training_point_in_time"

    for statement in downstream:
        assert statement in sql
        assert sql.index(statement) < sql.index(base_drop)

    # Avoid broad CASCADE: the migration should only tear down Decision Engine
    # views that it knows will be recreated by SQL 11/12 later in the installer.
    assert "drop view if exists features.separation_fall_training_point_in_time cascade" not in sql
