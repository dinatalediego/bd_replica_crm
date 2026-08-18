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


def test_transfer_lineage_is_explicitly_post_outcome_only() -> None:
    sql = SQL.read_text(encoding="utf-8").lower()
    assert "'post_outcome_audit_only'::text as lineage_evidence_role" in sql
    assert "false::boolean as lineage_live_feature_eligible" in sql
    assert "v_department_transfer_lineage_health" in sql
