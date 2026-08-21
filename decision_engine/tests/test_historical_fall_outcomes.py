from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
OUTCOME_SQL = ROOT / "sql" / "06_historical_fall_outcomes.sql"
ANALYSIS_SQL = ROOT / "sql" / "07_fall_reason_analysis_corpus.sql"
CURRENT_FEATURE_SQL = ROOT / "sql" / "02_separation_fall_risk_features.sql"
NLP_SCRIPT = REPO_ROOT / "scripts" / "analyze_fall_reason_text.py"


def test_historical_outcome_contract_reads_requested_proforma_text_fields() -> None:
    sql = OUTCOME_SQL.read_text(encoding="utf-8").lower()

    assert "raw_cygnus.datos_extras" in sql
    assert "motivo_caida_segun_asesor" in sql
    assert "cambio_de_departamento" in sql
    assert "depa_del_cambio" in sql
    assert "de.codigo::text" in sql
    assert "fecha_actualizacion desc nulls last" in sql


def test_temporal_target_follows_certified_core_competing_event_result() -> None:
    sql = " ".join(OUTCOME_SQL.read_text(encoding="utf-8").lower().split())

    assert "target_fall_before_conversion" in sql
    assert "when c.resultado_ciclo = 'venta' then 0" in sql
    assert "when c.resultado_ciclo = 'caida' then 1" in sql
    assert "conversion_interest_sample" in sql
    assert "conversion_interest_without_temporal_label" in sql
    assert "falls_with_payment_evidence_now_for_temporal_review" in sql


def test_fall_reason_is_explicitly_post_outcome_and_not_live_feature() -> None:
    outcome_sql = OUTCOME_SQL.read_text(encoding="utf-8").lower()
    analysis_sql = ANALYSIS_SQL.read_text(encoding="utf-8").lower()
    current_sql = CURRENT_FEATURE_SQL.read_text(encoding="utf-8").lower()

    assert "'post_outcome_only'::text as fall_reason_text_role" in outcome_sql
    assert "false::boolean as fall_reason_live_feature_eligible" in outcome_sql
    assert "'post_outcome_only'::text as reason_evidence_role" in analysis_sql
    assert "false::boolean as reason_evidence_live_feature_eligible" in analysis_sql
    assert "motivo_caida_segun_asesor" not in current_sql
    assert "cambio_de_departamento" not in current_sql
    assert "depa_del_cambio" not in current_sql


def test_text_corpus_is_deduplicated_at_proforma_grain() -> None:
    sql = " ".join(OUTCOME_SQL.read_text(encoding="utf-8").lower().split())

    assert "partition by h.codigo_proforma" in sql
    assert "where h.target_fall_before_conversion = 1" in sql
    assert "v_fall_reason_proforma_history" in sql


def test_analysis_corpus_keeps_structured_change_without_free_text() -> None:
    sql = " ".join(ANALYSIS_SQL.read_text(encoding="utf-8").lower().split())

    assert "v_fall_reason_analysis_corpus" in sql
    assert "structured_change_only" in sql
    assert "has_confirmed_department_change" in sql
    assert "depa_del_cambio" in sql
    assert "like '%cambi%'" in sql


def test_nlp_script_is_exploratory_self_contained_and_uses_structured_evidence() -> None:
    code = NLP_SCRIPT.read_text(encoding="utf-8")

    assert "TfidfVectorizer" in code
    assert "NMF" in code
    assert "POST_OUTCOME_ONLY" in code
    assert "v_fall_reason_analysis_corpus" in code
    assert "reason_tags" in code
    assert "is_confirmed_department_change" in code
    assert '"se cayo"' in code
    assert "separation_fall_risk_current" not in code
