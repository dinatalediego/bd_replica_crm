from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql" / "117_decision_room_funnel" / "01_contract.sql").read_text(encoding="utf-8")


def test_identity_audit_view_is_aggregate_and_classifies_source_semantics():
    lowered = SQL.lower()
    assert "analytics.v_decision_room_identity_audit_monthly" in lowered
    assert "person_project_entry_like" in lowered
    assert "multi_event_lead_like" in lowered
    assert "repeated_person_project_rows" in lowered
    assert "multi_project_documents" in lowered


def test_cohort_view_anchors_on_first_lead_and_rejects_past_events():
    lowered = SQL.lower()
    assert "analytics.v_decision_room_funnel_cohort_monthly" in lowered
    assert "fecha_primer_lead" in lowered
    assert "proforma_date >= b.lead_date" in lowered
    assert "separation_date >= b.lead_date" in lowered
    assert "minuta_date >= b.lead_date" in lowered
    assert "temporal_anomaly" in lowered


def test_cohort_contract_has_mature_30_60_90_day_denominators():
    lowered = SQL.lower()
    for horizon in (30, 60, 90):
        assert f"eligible_{horizon}d" in lowered
        assert f"lead_to_proforma_{horizon}d_rate" in lowered
        assert f"lead_to_separacion_{horizon}d_rate" in lowered
        assert f"lead_to_minuta_{horizon}d_rate" in lowered
    assert "lead_cohort_realized_as_of_cutoff" in lowered
