from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "09_transfer_lineage_audit.sql"


def test_transfer_lineage_audit_uses_same_client_successor_separation() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "p.documento_cliente::text = t.documento_cliente::text" in sql
    assert "p.codigo_proforma::text <> t.codigo_proforma" in sql
    assert "p.fecha_inicio::date <= t.primera_fecha_caida::date + 90" in sql


def test_transfer_lineage_prefers_declared_destination_match_when_available() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "declared_destination_norm" in sql
    assert "destination_match_score" in sql
    assert "core.dim_unidad" in sql
    assert "core.dim_proyecto" in sql
    assert "verified_destination_within_30d" in sql
    assert "destination_mismatch" in sql
    assert "destination_unverifiable" in sql
    assert "s.destination_match_score >= 2" in sql
    assert "unit_number_only_match_weak" in sql


def test_transfer_lineage_distinguishes_right_censoring_from_no_successor() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "max(fecha_inicio)::date as observed_through" in sql
    assert "pending_successor_observation_90d" in sql
    assert "reported_no_successor_after_90d" in sql
    assert "successor_observation_window_complete_90d" in sql


def test_transfer_lineage_surfaces_declared_destination_equal_to_origin() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "declared_destination_matches_origin" in sql
    assert "origin_nombre_unidad" in sql
    assert "declared_destination_matches_origin_rows" in sql


def test_transfer_base_reuses_governed_reason_fields_without_duplicate_names() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "coalesce(t.depa_del_cambio, '')" in sql
    assert "a.cambio_de_departamento" not in sql
    assert "a.depa_del_cambio" not in sql
    assert "a.motivo_caida_segun_asesor" not in sql


def test_transfer_views_are_rebuilt_when_projection_changes() -> None:
    sql = " ".join(SQL.read_text(encoding="utf-8").lower().split())
    assert "drop view if exists decision_intelligence.v_department_transfer_lineage_health" in sql
    assert "drop view if exists decision_intelligence.v_department_transfer_lineage_audit" in sql
    assert "create view decision_intelligence.v_department_transfer_lineage_audit" in sql


def test_transfer_lineage_is_explicitly_post_outcome_only() -> None:
    sql = SQL.read_text(encoding="utf-8").lower()
    assert "'post_outcome_audit_only'::text as lineage_evidence_role" in sql
    assert "false::boolean as lineage_live_feature_eligible" in sql
    assert "v_department_transfer_lineage_health" in sql
