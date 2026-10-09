BEGIN;

CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ===============================================================
-- Forecast Factory v1.0.1
-- Horizon semantics + honest intervals + legacy bridge support
-- ===============================================================

-- 1) Do not fabricate intervals when temporal support is insufficient.
ALTER TABLE analytics.forecast_prediction_v1
    ALTER COLUMN prediction_lower DROP NOT NULL,
    ALTER COLUMN prediction_upper DROP NOT NULL;

-- 2) Forecast semantics: a target may be a period value or cumulative window.
ALTER TABLE analytics.forecast_prediction_v1
    ADD COLUMN IF NOT EXISTS origin_period date,
    ADD COLUMN IF NOT EXISTS forecast_window_start date,
    ADD COLUMN IF NOT EXISTS forecast_window_end date,
    ADD COLUMN IF NOT EXISTS aggregation_semantics text NOT NULL DEFAULT 'PERIOD_VALUE',
    ADD COLUMN IF NOT EXISTS scope_semantics text,
    ADD COLUMN IF NOT EXISTS source_system text,
    ADD COLUMN IF NOT EXISTS source_run_ref text,
    ADD COLUMN IF NOT EXISTS source_model_ref text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='analytics.forecast_prediction_v1'::regclass
          AND conname='forecast_prediction_v1_aggregation_semantics_check'
    ) THEN
        ALTER TABLE analytics.forecast_prediction_v1
        ADD CONSTRAINT forecast_prediction_v1_aggregation_semantics_check
        CHECK (aggregation_semantics IN ('PERIOD_VALUE','CUMULATIVE_WINDOW'));
    END IF;
END $$;

-- 3) Expand evidence class honestly: SHADOW is issued evidence that is not
-- allowed to masquerade as strict prospective evidence.
ALTER TABLE analytics.forecast_prediction_v1
    DROP CONSTRAINT IF EXISTS forecast_prediction_v1_evidence_class_check;

ALTER TABLE analytics.forecast_prediction_v1
    ADD CONSTRAINT forecast_prediction_v1_evidence_class_check
    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST','SHADOW'));

ALTER TABLE analytics.forecast_evaluation_v1
    DROP CONSTRAINT IF EXISTS forecast_evaluation_v1_evidence_class_check;

ALTER TABLE analytics.forecast_evaluation_v1
    ADD CONSTRAINT forecast_evaluation_v1_evidence_class_check
    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST','SHADOW'));

-- Evidence table already has governance semantics; expand it too.
ALTER TABLE model_control.forecast_evidence_v1
    DROP CONSTRAINT IF EXISTS forecast_evidence_v1_evidence_class_check;

ALTER TABLE model_control.forecast_evidence_v1
    ADD CONSTRAINT forecast_evidence_v1_evidence_class_check
    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST','SHADOW','GOVERNANCE'));


-- 4) Existing Medallio commercial forecasting evaluates cumulative windows,
-- so keep a canonical cumulative-window actual ledger rather than forcing it
-- into a one-month actual grain.
CREATE TABLE IF NOT EXISTS analytics.forecast_actual_window_v101 (
    actual_window_id bigserial PRIMARY KEY,

    project_key text NOT NULL,
    target_name text NOT NULL,
    target_unit text NOT NULL,
    segment_key text NOT NULL DEFAULT 'ALL',

    origin_period date NOT NULL,
    forecast_window_start date NOT NULL,
    forecast_window_end date NOT NULL,
    horizon_months integer NOT NULL,

    aggregation_semantics text NOT NULL DEFAULT 'CUMULATIVE_WINDOW',
    scope_semantics text NOT NULL,

    actual_value numeric NOT NULL,
    period_complete boolean NOT NULL DEFAULT true,
    compatible_scope boolean NOT NULL DEFAULT true,

    source_system text NOT NULL,
    source_run_ref text,
    source_snapshot_id text,
    source_reference text,

    period_closed_at timestamptz,
    loaded_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(
        project_key, target_name, segment_key,
        origin_period, forecast_window_end,
        aggregation_semantics, scope_semantics
    ),

    CHECK (horizon_months >= 1),
    CHECK (aggregation_semantics='CUMULATIVE_WINDOW')
);


-- 5) Idempotent mapping from old UUID runs to canonical BIGINT runs.
CREATE TABLE IF NOT EXISTS model_control.forecast_legacy_run_map_v101 (
    source_system text NOT NULL,
    legacy_run_id text NOT NULL,
    legacy_model text NOT NULL,
    canonical_model_version_id bigint NOT NULL
        REFERENCES model_control.forecast_model_registry_v1(model_version_id),
    canonical_run_id bigint NOT NULL UNIQUE
        REFERENCES model_control.forecast_run_v1(run_id),
    bridged_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(source_system, legacy_run_id, legacy_model)
);


-- 6) Contract compliance v1.0.1: missing interval is a contract state, not
-- an insertion failure.
CREATE OR REPLACE VIEW model_control.v_forecast_run_contract_compliance_v101 AS
SELECT
    r.run_id,
    r.model_version_id,
    mr.model_name,
    mr.model_version,
    mr.target_name AS registry_target_name,
    r.issued_at,
    r.data_cutoff_date,

    count(p.prediction_id) AS prediction_rows,

    bool_and(p.naive_method IS NOT NULL AND btrim(p.naive_method) <> '') AS has_naive_method,
    bool_and(p.naive_prediction IS NOT NULL) AS has_naive_prediction,
    bool_and(p.horizon_months >= 1) AS horizons_valid,

    bool_and(
        CASE
            WHEN p.aggregation_semantics='CUMULATIVE_WINDOW'
            THEN p.origin_period IS NOT NULL
             AND p.forecast_window_start IS NOT NULL
             AND p.forecast_window_end IS NOT NULL
            ELSE true
        END
    ) AS window_semantics_valid,

    count(*) FILTER (
        WHERE p.prediction_lower IS NULL OR p.prediction_upper IS NULL
    ) AS predictions_without_interval,

    bool_and(
        CASE
            WHEN p.evidence_class='PROSPECTIVE'
            THEN p.data_cutoff_date_copy < p.forecast_window_start
            ELSE true
        END
    ) AS prospective_temporal_order_valid,

    CASE
        WHEN count(p.prediction_id)=0 THEN 'NO_PREDICTIONS'
        WHEN NOT bool_and(p.naive_method IS NOT NULL AND btrim(p.naive_method) <> '') THEN 'MISSING_NAIVE'
        WHEN NOT bool_and(p.naive_prediction IS NOT NULL) THEN 'MISSING_NAIVE'
        WHEN NOT bool_and(p.horizon_months >= 1) THEN 'INVALID_HORIZON'
        WHEN NOT bool_and(
            CASE
                WHEN p.aggregation_semantics='CUMULATIVE_WINDOW'
                THEN p.origin_period IS NOT NULL
                 AND p.forecast_window_start IS NOT NULL
                 AND p.forecast_window_end IS NOT NULL
                ELSE true
            END
        ) THEN 'INVALID_WINDOW_SEMANTICS'
        WHEN NOT bool_and(
            CASE
                WHEN p.evidence_class='PROSPECTIVE'
                THEN p.data_cutoff_date_copy < p.forecast_window_start
                ELSE true
            END
        ) THEN 'TEMPORAL_LEAKAGE_RISK'
        WHEN count(*) FILTER (
            WHERE p.prediction_lower IS NULL OR p.prediction_upper IS NULL
        ) > 0 THEN 'INTERVAL_INCUBATING'
        ELSE 'PASS'
    END AS contract_status

FROM model_control.forecast_run_v1 r
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
LEFT JOIN analytics.forecast_prediction_v1 p
  ON p.run_id=r.run_id
GROUP BY
    r.run_id, r.model_version_id, mr.model_name,
    mr.model_version, mr.target_name, r.issued_at, r.data_cutoff_date;


-- 7) Unified maturity clock supporting both one-period and cumulative-window targets.
CREATE OR REPLACE VIEW analytics.v_forecast_maturity_clock_v101 AS
WITH period_target AS (
    SELECT
        p.prediction_id,
        p.run_id,
        p.project_key,
        p.target_name,
        p.target_unit,
        p.segment_key,
        p.origin_period,
        p.forecast_window_start,
        p.forecast_window_end,
        p.forecast_for_period,
        p.horizon_months,
        p.aggregation_semantics,
        p.scope_semantics,
        p.evidence_class,
        p.prediction,
        p.prediction_lower,
        p.prediction_upper,
        p.naive_method,
        p.naive_prediction,
        p.issued_at_copy AS issued_at,
        p.data_cutoff_date_copy AS data_cutoff_date,
        a.actual_id::bigint AS actual_ref_id,
        a.actual_value,
        a.period_complete,
        true AS compatible_scope,
        a.period_closed_at,
        CASE
            WHEN p.prediction_status='INVALIDATED' THEN 'INVALIDATED'
            WHEN a.actual_id IS NULL THEN 'INCUBATING'
            WHEN NOT a.period_complete THEN 'INCUBATING'
            ELSE 'MATURE'
        END AS maturity_status
    FROM analytics.forecast_prediction_v1 p
    LEFT JOIN analytics.forecast_actual_v1 a
      ON p.aggregation_semantics='PERIOD_VALUE'
     AND a.project_key=p.project_key
     AND a.target_name=p.target_name
     AND a.segment_key=p.segment_key
     AND a.actual_period=p.forecast_for_period
    WHERE p.aggregation_semantics='PERIOD_VALUE'
),
window_target AS (
    SELECT
        p.prediction_id,
        p.run_id,
        p.project_key,
        p.target_name,
        p.target_unit,
        p.segment_key,
        p.origin_period,
        p.forecast_window_start,
        p.forecast_window_end,
        p.forecast_for_period,
        p.horizon_months,
        p.aggregation_semantics,
        p.scope_semantics,
        p.evidence_class,
        p.prediction,
        p.prediction_lower,
        p.prediction_upper,
        p.naive_method,
        p.naive_prediction,
        p.issued_at_copy AS issued_at,
        p.data_cutoff_date_copy AS data_cutoff_date,
        a.actual_window_id::bigint AS actual_ref_id,
        a.actual_value,
        a.period_complete,
        a.compatible_scope,
        a.period_closed_at,
        CASE
            WHEN p.prediction_status='INVALIDATED' THEN 'INVALIDATED'
            WHEN a.actual_window_id IS NULL THEN 'INCUBATING'
            WHEN NOT a.period_complete THEN 'INCUBATING'
            WHEN NOT a.compatible_scope THEN 'BLOCKED_SCOPE'
            ELSE 'MATURE'
        END AS maturity_status
    FROM analytics.forecast_prediction_v1 p
    LEFT JOIN analytics.forecast_actual_window_v101 a
      ON p.aggregation_semantics='CUMULATIVE_WINDOW'
     AND a.project_key=p.project_key
     AND a.target_name=p.target_name
     AND a.segment_key=p.segment_key
     AND a.origin_period=p.origin_period
     AND a.forecast_window_end=p.forecast_window_end
     AND a.scope_semantics=p.scope_semantics
    WHERE p.aggregation_semantics='CUMULATIVE_WINDOW'
)
SELECT * FROM period_target
UNION ALL
SELECT * FROM window_target;


CREATE OR REPLACE VIEW analytics.v_forecast_mature_pairs_v101 AS
SELECT
    mc.*,

    (mc.prediction - mc.actual_value) AS signed_error,
    abs(mc.prediction - mc.actual_value) AS absolute_error,

    CASE
        WHEN abs(mc.actual_value) > 0
        THEN abs(mc.prediction - mc.actual_value) / abs(mc.actual_value)
        ELSE NULL
    END AS ape,

    (mc.naive_prediction - mc.actual_value) AS naive_signed_error,
    abs(mc.naive_prediction - mc.actual_value) AS naive_absolute_error,

    CASE
        WHEN abs(mc.actual_value) > 0
        THEN abs(mc.naive_prediction - mc.actual_value) / abs(mc.actual_value)
        ELSE NULL
    END AS naive_ape,

    CASE
        WHEN mc.prediction_lower IS NULL OR mc.prediction_upper IS NULL
        THEN NULL
        ELSE mc.actual_value BETWEEN mc.prediction_lower AND mc.prediction_upper
    END AS interval_hit,

    CASE
        WHEN mc.prediction_lower IS NULL OR mc.prediction_upper IS NULL
        THEN NULL
        ELSE mc.prediction_upper - mc.prediction_lower
    END AS interval_width,

    CASE
        WHEN mc.evidence_class='PROSPECTIVE'
        THEN mc.issued_at < mc.period_closed_at
         AND mc.data_cutoff_date < mc.forecast_window_start
        WHEN mc.evidence_class IN ('BACKTEST','SHADOW')
        THEN false
        ELSE false
    END AS leakage_safe

FROM analytics.v_forecast_maturity_clock_v101 mc
WHERE mc.maturity_status='MATURE';


CREATE OR REPLACE VIEW analytics.v_forecast_performance_v101 AS
SELECT
    mp.run_id,
    r.model_version_id,
    mr.model_name,
    mr.model_version,
    mr.model_family,

    mp.project_key,
    mp.target_name,
    mp.target_unit,
    mp.segment_key,
    mp.horizon_months,
    mp.aggregation_semantics,
    mp.scope_semantics,
    mp.evidence_class,

    count(*) AS mature_pairs,
    count(*) FILTER (WHERE mp.leakage_safe) AS leakage_safe_pairs,

    sum(mp.absolute_error)
        / nullif(sum(abs(mp.actual_value)),0) AS wape,

    sum(mp.signed_error)
        / nullif(sum(abs(mp.actual_value)),0) AS bias,

    sum(mp.naive_absolute_error)
        / nullif(sum(abs(mp.actual_value)),0) AS naive_wape,

    1 - (
        (sum(mp.absolute_error) / nullif(sum(abs(mp.actual_value)),0))
        /
        nullif(
            (sum(mp.naive_absolute_error) / nullif(sum(abs(mp.actual_value)),0)),
            0
        )
    ) AS skill_vs_naive,

    avg(
        CASE
            WHEN mp.interval_hit IS NULL THEN NULL
            WHEN mp.interval_hit THEN 1.0
            ELSE 0.0
        END
    ) AS interval_coverage,

    avg(mp.interval_width) AS avg_interval_width,

    min(mp.forecast_window_end) AS first_mature_period,
    max(mp.forecast_window_end) AS latest_mature_period

FROM analytics.v_forecast_mature_pairs_v101 mp
JOIN model_control.forecast_run_v1 r
  ON r.run_id=mp.run_id
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
GROUP BY
    mp.run_id, r.model_version_id, mr.model_name, mr.model_version,
    mr.model_family, mp.project_key, mp.target_name, mp.target_unit,
    mp.segment_key, mp.horizon_months, mp.aggregation_semantics,
    mp.scope_semantics, mp.evidence_class;


CREATE OR REPLACE VIEW analytics.v_forecast_defendability_v101 AS
WITH policy AS (
    SELECT *
    FROM model_control.forecast_gate_policy_v1
    WHERE is_active
    ORDER BY policy_id
    LIMIT 1
)
SELECT
    perf.*,
    p.policy_name,
    p.wape_threshold,
    p.min_mature_pairs,
    p.min_skill_vs_naive,
    p.min_interval_coverage,

    CASE
        WHEN p.prospective_only AND perf.evidence_class <> 'PROSPECTIVE'
            THEN 'BLOCK'
        WHEN perf.mature_pairs < p.min_mature_pairs
            THEN 'INCUBATING'
        WHEN perf.leakage_safe_pairs < perf.mature_pairs
            THEN 'BLOCK'
        WHEN perf.wape IS NULL OR perf.naive_wape IS NULL
            THEN 'BLOCK'
        WHEN perf.wape > p.wape_threshold
            THEN 'WARN'
        WHEN perf.skill_vs_naive < p.min_skill_vs_naive
            THEN 'WARN'
        WHEN perf.interval_coverage IS NULL
            THEN 'INCUBATING'
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'WARN'
        ELSE 'PASS'
    END AS defendability_status,

    CASE
        WHEN p.prospective_only AND perf.evidence_class <> 'PROSPECTIVE'
            THEN 'Evidence is not strict prospective evidence.'
        WHEN perf.mature_pairs < p.min_mature_pairs
            THEN 'Not enough mature prospective pairs.'
        WHEN perf.leakage_safe_pairs < perf.mature_pairs
            THEN 'At least one mature pair fails leakage-safety checks.'
        WHEN perf.wape > p.wape_threshold
            THEN 'WAPE is above policy threshold.'
        WHEN perf.skill_vs_naive < p.min_skill_vs_naive
            THEN 'Model does not beat the naive benchmark.'
        WHEN perf.interval_coverage IS NULL
            THEN 'Prediction intervals are still incubating.'
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'Prediction interval coverage is below policy threshold.'
        ELSE 'Forecast evidence satisfies the active policy.'
    END AS defendability_reason

FROM analytics.v_forecast_performance_v101 perf
CROSS JOIN policy p;


-- Power BI v1.0.1 stable surfaces.
CREATE OR REPLACE VIEW analytics.v_pbi_forecast_factory_current_v101 AS
SELECT
    p.prediction_id,
    p.run_id,
    mr.model_name,
    mr.model_version,
    mr.model_family,
    mr.lifecycle_status,

    p.project_key,
    p.target_name,
    p.target_unit,
    p.segment_key,

    p.origin_period,
    p.forecast_window_start,
    p.forecast_window_end,
    p.forecast_for_period,
    p.horizon_months,
    p.aggregation_semantics,
    p.scope_semantics,

    p.prediction,
    p.prediction_lower,
    p.prediction_upper,
    p.interval_level,

    p.naive_method,
    p.naive_prediction,

    p.evidence_class,
    p.prediction_status,

    r.issued_at,
    r.data_cutoff_date,
    r.feature_version,
    r.dataset_snapshot_id,
    r.code_sha,

    mc.maturity_status,
    mc.actual_value,
    mc.period_closed_at,

    p.source_system,
    p.source_run_ref,
    p.source_model_ref,

    (p.metadata->>'is_selected')::boolean AS is_selected

FROM analytics.forecast_prediction_v1 p
JOIN model_control.forecast_run_v1 r
  ON r.run_id=p.run_id
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
LEFT JOIN analytics.v_forecast_maturity_clock_v101 mc
  ON mc.prediction_id=p.prediction_id
WHERE r.run_status='ISSUED';


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_performance_v101 AS
SELECT
    d.*,
    rc.contract_status AS run_contract_status,
    rc.predictions_without_interval
FROM analytics.v_forecast_defendability_v101 d
LEFT JOIN model_control.v_forecast_run_contract_compliance_v101 rc
  ON rc.run_id=d.run_id;


COMMENT ON VIEW analytics.v_forecast_maturity_clock_v101 IS
'Supports period-value and cumulative-window forecasts without mixing target semantics.';
COMMENT ON TABLE analytics.forecast_actual_window_v101 IS
'Canonical actual ledger for cumulative forecast windows such as current-stock sales through horizon H.';

COMMIT;
