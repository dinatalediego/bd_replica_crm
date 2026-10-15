BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS model_control;

-- ================================================================
-- Medallio v2.8.4 — Pre-Maturity Control & Execution Readiness
--
-- This layer DOES NOT promote L3.
-- It answers what can be governed while prospective forecasts mature:
-- 1) which captures are truly eligible forecasts vs current-period nowcasts,
-- 2) whether benchmark/traceability coverage is ready before maturity,
-- 3) which governed decisions still have no action/outcome loop.
-- ================================================================

CREATE OR REPLACE VIEW analytics.v_forecast_issue_quality_v284 AS
WITH bench AS (
    SELECT
        issue_id,
        count(*) AS benchmark_methods,
        bool_or(primary_benchmark) AS has_primary_benchmark
    FROM model_control.forecast_naive_benchmark_snapshot
    GROUP BY issue_id
),
canonical AS (
    SELECT issue_id
    FROM model_control.v_forecast_issue_canonical
),
clock AS (
    SELECT issue_id, maturity_status, expected_maturity_date,
           days_until_expected_maturity
    FROM analytics.v_forecast_maturity_clock_v283
)
SELECT
    i.issue_id,
    i.issue_batch_id,
    i.slot,
    i.source_relation,
    i.source_run_id,
    i.issued_at,
    (i.issued_at AT TIME ZONE 'America/Lima')::date AS issue_date_lima,
    date_trunc('month', i.issued_at AT TIME ZONE 'America/Lima')::date AS issue_month_lima,
    i.data_cutoff,

    i.project_key,
    i.origin_period,
    i.target_period,
    i.horizon,
    i.prediction,
    i.model_name,
    i.model_version,
    i.stock_at_issue,

    CASE
        WHEN (i.issued_at AT TIME ZONE 'America/Lima')::date < i.target_period
            THEN 'PROSPECTIVE_ELIGIBLE'
        WHEN date_trunc('month', i.issued_at AT TIME ZONE 'America/Lima')::date = i.target_period
            THEN 'CURRENT_PERIOD_NOWCAST'
        ELSE 'LATE_OR_RETROSPECTIVE'
    END AS issuance_class,

    CASE
        WHEN i.origin_period IS NULL THEN NULL
        ELSE i.target_period = (
            i.origin_period + make_interval(months => i.horizon)
        )::date
    END AS horizon_alignment_ok,

    (c.issue_id IS NOT NULL) AS canonical_active,
    coalesce(b.benchmark_methods, 0) AS benchmark_methods,
    coalesce(b.has_primary_benchmark, false) AS has_primary_benchmark,

    (i.source_run_id IS NOT NULL) AS has_source_run_id,
    (i.model_name IS NOT NULL) AS has_model_name,
    (i.model_version IS NOT NULL) AS has_model_version,
    (i.data_cutoff IS NOT NULL) AS has_data_cutoff,

    cl.maturity_status,
    cl.expected_maturity_date,
    cl.days_until_expected_maturity,

    CASE
        WHEN i.prediction < 0 THEN 'INVALID_NEGATIVE_PREDICTION'
        WHEN i.stock_at_issue IS NOT NULL AND i.prediction > i.stock_at_issue
            THEN 'CHECK_PREDICTION_ABOVE_STOCK'
        WHEN i.origin_period IS NOT NULL
         AND i.target_period <> (i.origin_period + make_interval(months => i.horizon))::date
            THEN 'CHECK_HORIZON_ALIGNMENT'
        WHEN c.issue_id IS NOT NULL AND NOT coalesce(b.has_primary_benchmark, false)
            THEN 'CHECK_MISSING_BENCHMARK'
        ELSE 'OK'
    END AS pre_maturity_quality_status

FROM model_control.forecast_issue_registry i
LEFT JOIN bench b ON b.issue_id = i.issue_id
LEFT JOIN canonical c ON c.issue_id = i.issue_id
LEFT JOIN clock cl ON cl.issue_id = i.issue_id;


CREATE OR REPLACE VIEW analytics.v_predictive_pre_maturity_readiness_v284 AS
WITH q AS (
    SELECT *
    FROM analytics.v_forecast_issue_quality_v284
),
latest_batch AS (
    SELECT *
    FROM model_control.forecast_issue_batch
    ORDER BY issued_at DESC, created_at DESC
    LIMIT 1
),
summary AS (
    SELECT
        count(*) AS captured_total,
        count(*) FILTER (WHERE issuance_class = 'PROSPECTIVE_ELIGIBLE') AS prospective_eligible,
        count(*) FILTER (WHERE issuance_class = 'CURRENT_PERIOD_NOWCAST') AS current_period_nowcast,
        count(*) FILTER (WHERE issuance_class = 'LATE_OR_RETROSPECTIVE') AS late_or_retrospective,

        count(*) FILTER (WHERE canonical_active) AS active_forecast_cells,
        count(*) FILTER (WHERE canonical_active AND maturity_status = 'INCUBATING') AS incubating,
        count(*) FILTER (WHERE canonical_active AND maturity_status = 'EVALUATED') AS evaluated,
        count(*) FILTER (WHERE canonical_active AND maturity_status = 'OVERDUE_NO_ACTUAL') AS overdue_no_actual,

        count(*) FILTER (WHERE canonical_active AND has_primary_benchmark) AS benchmarked_active,
        count(*) FILTER (WHERE canonical_active AND horizon_alignment_ok IS TRUE) AS horizon_aligned_active,
        count(*) FILTER (WHERE canonical_active AND has_source_run_id) AS run_traceable_active,
        count(*) FILTER (WHERE canonical_active AND has_model_name) AS model_named_active,
        count(*) FILTER (WHERE canonical_active AND has_model_version) AS model_versioned_active,
        count(*) FILTER (WHERE canonical_active AND has_data_cutoff) AS data_cutoff_active,

        count(*) FILTER (
            WHERE canonical_active AND pre_maturity_quality_status <> 'OK'
        ) AS quality_exceptions_active,

        min(expected_maturity_date) FILTER (
            WHERE canonical_active AND maturity_status = 'INCUBATING'
        ) AS next_maturity_date,

        count(DISTINCT project_key) FILTER (WHERE canonical_active) AS projects_active,
        count(DISTINCT horizon) FILTER (WHERE canonical_active) AS horizons_active
    FROM q
)
SELECT
    s.*,

    round(100.0 * s.prospective_eligible / nullif(s.captured_total, 0), 1)
        AS prospective_eligibility_pct,

    round(100.0 * s.benchmarked_active / nullif(s.active_forecast_cells, 0), 1)
        AS benchmark_coverage_pct,

    round(100.0 * s.horizon_aligned_active / nullif(s.active_forecast_cells, 0), 1)
        AS horizon_alignment_pct,

    round(100.0 * s.run_traceable_active / nullif(s.active_forecast_cells, 0), 1)
        AS source_run_coverage_pct,

    round(100.0 * s.model_versioned_active / nullif(s.active_forecast_cells, 0), 1)
        AS model_version_coverage_pct,

    round(100.0 * s.data_cutoff_active / nullif(s.active_forecast_cells, 0), 1)
        AS data_cutoff_coverage_pct,

    CASE
        WHEN s.active_forecast_cells = 0 THEN 'BLOCK'
        WHEN 100.0 * s.benchmarked_active / nullif(s.active_forecast_cells, 0) < 90 THEN 'BLOCK'
        WHEN 100.0 * s.horizon_aligned_active / nullif(s.active_forecast_cells, 0) < 100 THEN 'BLOCK'
        WHEN s.quality_exceptions_active > 0 THEN 'WARN'
        ELSE 'READY_TO_INCUBATE'
    END AS pre_maturity_status,

    CASE
        WHEN s.active_forecast_cells = 0
            THEN 'No existen forecasts prospectivos activos.'
        WHEN 100.0 * s.benchmarked_active / nullif(s.active_forecast_cells, 0) < 90
            THEN 'Cobertura de benchmark inferior a 90%.'
        WHEN 100.0 * s.horizon_aligned_active / nullif(s.active_forecast_cells, 0) < 100
            THEN 'Existen forecasts con desalineación origin→horizon→target.'
        WHEN s.quality_exceptions_active > 0
            THEN concat('Hay ', s.quality_exceptions_active, ' excepciones de calidad pre-madurez por revisar.')
        ELSE 'La fábrica predictiva está lista para incubar evidencia; no implica L3 PASS.'
    END AS pre_maturity_reason,

    lb.issue_batch_id AS latest_batch_id,
    lb.slot AS latest_batch_slot,
    lb.source_rows AS latest_source_rows,
    lb.candidate_cells AS latest_candidate_cells,
    lb.inserted_rows AS latest_inserted_rows,
    lb.unchanged_rows AS latest_unchanged_rows,
    lb.ambiguous_cells AS latest_ambiguous_cells,
    lb.capture_status AS latest_capture_status

FROM summary s
LEFT JOIN latest_batch lb ON true;


-- Latest governed decision instance per project/title.
CREATE OR REPLACE VIEW decision_intelligence.v_decision_execution_gap_v284 AS
WITH latest AS (
    SELECT *
    FROM (
        SELECT
            d.*,
            row_number() OVER (
                PARTITION BY coalesce(d.project_key, 'PORTFOLIO'), d.decision_title
                ORDER BY d.decision_ts DESC, d.created_at DESC, d.decision_id DESC
            ) AS rn
        FROM decision_intelligence.decision_ledger d
    ) x
    WHERE rn = 1
),
actions AS (
    SELECT
        decision_id,
        count(*) AS action_count,
        count(*) FILTER (WHERE action_status = 'OPEN') AS open_action_count,
        count(*) FILTER (WHERE action_status = 'DONE') AS done_action_count,
        min(expected_completion_at) FILTER (WHERE action_status = 'OPEN') AS next_action_due
    FROM decision_intelligence.action_log
    GROUP BY decision_id
),
outcomes AS (
    SELECT
        decision_id,
        count(*) AS outcome_count,
        count(*) FILTER (WHERE maturity_status = 'MATURE') AS mature_outcome_count,
        max(outcome_ts) AS latest_outcome_ts,
        sum(value_realized) AS realized_value_total
    FROM decision_intelligence.outcome_ledger
    GROUP BY decision_id
)
SELECT
    d.decision_id,
    d.decision_ts,
    d.project_key,
    d.challenge,
    d.decision_title,
    d.owner,
    d.deadline,
    d.decision_status,
    d.decision_level,
    d.quantification_status,
    d.value_at_risk,
    d.value_to_capture,
    d.action_cost,
    d.expected_roi,

    coalesce(a.action_count, 0) AS action_count,
    coalesce(a.open_action_count, 0) AS open_action_count,
    coalesce(a.done_action_count, 0) AS done_action_count,
    a.next_action_due,

    coalesce(o.outcome_count, 0) AS outcome_count,
    coalesce(o.mature_outcome_count, 0) AS mature_outcome_count,
    o.latest_outcome_ts,
    o.realized_value_total,

    CASE
        WHEN d.owner IS NULL OR btrim(d.owner) = '' THEN 'NEEDS_OWNER'
        WHEN d.deadline IS NULL THEN 'NEEDS_DEADLINE'
        WHEN coalesce(a.action_count, 0) = 0 THEN 'NEEDS_ACTION'
        WHEN coalesce(a.open_action_count, 0) > 0 THEN 'ACTION_IN_PROGRESS'
        WHEN coalesce(a.done_action_count, 0) > 0 AND coalesce(o.outcome_count, 0) = 0
            THEN 'WAITING_OUTCOME'
        WHEN coalesce(o.mature_outcome_count, 0) = 0 THEN 'OUTCOME_IMMATURE'
        ELSE 'LEARNING_COMPLETE'
    END AS execution_status,

    CASE
        WHEN coalesce(a.action_count, 0) = 0
            THEN 'Convertir la recomendación en acción con owner, deadline y métrica de éxito.'
        WHEN coalesce(a.open_action_count, 0) > 0
            THEN 'Ejecutar y registrar evidencia de la acción.'
        WHEN coalesce(o.outcome_count, 0) = 0
            THEN 'Registrar outcome y valor realizado.'
        WHEN coalesce(o.mature_outcome_count, 0) = 0
            THEN 'Esperar madurez del outcome sin promover causalidad.'
        ELSE 'Usar el outcome para aprendizaje y revisión de política.'
    END AS next_operational_step

FROM latest d
LEFT JOIN actions a ON a.decision_id = d.decision_id
LEFT JOIN outcomes o ON o.decision_id = d.decision_id;


CREATE OR REPLACE VIEW decision_intelligence.v_execution_control_tower_v284 AS
SELECT
    count(*) AS governed_decisions,
    count(*) FILTER (WHERE execution_status = 'NEEDS_OWNER') AS needs_owner,
    count(*) FILTER (WHERE execution_status = 'NEEDS_DEADLINE') AS needs_deadline,
    count(*) FILTER (WHERE execution_status = 'NEEDS_ACTION') AS needs_action,
    count(*) FILTER (WHERE execution_status = 'ACTION_IN_PROGRESS') AS action_in_progress,
    count(*) FILTER (WHERE execution_status = 'WAITING_OUTCOME') AS waiting_outcome,
    count(*) FILTER (WHERE execution_status = 'OUTCOME_IMMATURE') AS outcome_immature,
    count(*) FILTER (WHERE execution_status = 'LEARNING_COMPLETE') AS learning_complete,
    sum(open_action_count) AS open_actions,
    sum(outcome_count) AS outcomes,
    sum(mature_outcome_count) AS mature_outcomes
FROM decision_intelligence.v_decision_execution_gap_v284;


COMMENT ON VIEW analytics.v_predictive_pre_maturity_readiness_v284 IS
'Operational readiness while L3 evidence incubates. This view cannot promote L3; it controls issuance quality, benchmark coverage and traceability.';

COMMENT ON VIEW decision_intelligence.v_decision_execution_gap_v284 IS
'Governed decision queue converted into execution-loop status: owner → deadline → action → outcome → learning.';

COMMIT;
