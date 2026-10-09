BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS model_control;

-- ===============================================================
-- Medallio Forecast Factory v1.0.2
-- Prospective Issuance Clock + Lead-Time Forecasting
-- + Monthly Increment Adapter + Actual Loader support
-- ===============================================================

-- ---------------------------------------------------------------
-- 1. Extend canonical predictions with lineage + lead-time fields.
-- Existing rows remain valid.
-- ---------------------------------------------------------------
ALTER TABLE analytics.forecast_prediction_v1
    ADD COLUMN IF NOT EXISTS lead_time_days integer,
    ADD COLUMN IF NOT EXISTS lead_time_months integer,
    ADD COLUMN IF NOT EXISTS lead_time_bucket text,
    ADD COLUMN IF NOT EXISTS derivation_method text,
    ADD COLUMN IF NOT EXISTS source_prediction_id bigint,
    ADD COLUMN IF NOT EXISTS source_previous_prediction_id bigint,
    ADD COLUMN IF NOT EXISTS source_horizon_months integer;


-- ---------------------------------------------------------------
-- 2. Derived run mapping.
-- One derived monthly run for each cumulative source run.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_control.forecast_derived_run_map_v102 (
    derivation_method text NOT NULL,
    source_run_id bigint NOT NULL
        REFERENCES model_control.forecast_run_v1(run_id),
    derived_run_id bigint NOT NULL UNIQUE
        REFERENCES model_control.forecast_run_v1(run_id),
    source_model_version_id bigint NOT NULL
        REFERENCES model_control.forecast_model_registry_v1(model_version_id),
    derived_model_version_id bigint NOT NULL
        REFERENCES model_control.forecast_model_registry_v1(model_version_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(derivation_method, source_run_id)
);


-- ---------------------------------------------------------------
-- 3. Adapter audit.
-- We never silently clamp a negative monthly increment.
-- Non-monotonic cumulative forecasts are rejected and auditable.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_control.forecast_adapter_audit_v102 (
    audit_id bigserial PRIMARY KEY,
    derivation_method text NOT NULL,
    source_run_id bigint NOT NULL,
    project_key text NOT NULL,
    source_horizon_months integer NOT NULL,
    source_prediction_id bigint,
    source_previous_prediction_id bigint,
    target_period date NOT NULL,

    prediction_delta numeric,
    naive_delta numeric,

    adapter_status text NOT NULL,
    adapter_reason text,

    audited_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(
        derivation_method,
        source_run_id,
        project_key,
        source_horizon_months
    ),

    CHECK(adapter_status IN ('ACCEPTED','REJECTED'))
);


-- ---------------------------------------------------------------
-- 4. Actual revision ledger.
-- Closed actuals may be corrected later in CRM.
-- Current actual is canonical; revisions preserve auditability.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.forecast_actual_revision_v102 (
    revision_id bigserial PRIMARY KEY,
    actual_id bigint NOT NULL
        REFERENCES analytics.forecast_actual_v1(actual_id),

    project_key text NOT NULL,
    target_name text NOT NULL,
    segment_key text NOT NULL,
    actual_period date NOT NULL,

    old_actual_value numeric NOT NULL,
    new_actual_value numeric NOT NULL,

    revision_reason text NOT NULL,
    source_relation text NOT NULL,
    source_reference text,

    detected_at timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------
-- 5. Origin-dependent scope compatibility.
--
-- A cumulative/current-stock model predicts sales from stock that
-- existed at origin. Generic monthly sales are only comparable if
-- there were no material stock inflows after origin.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.forecast_scope_compatibility_v102 (
    project_key text NOT NULL,
    origin_period date NOT NULL,
    target_period date NOT NULL,
    scope_semantics text NOT NULL,

    compatible_scope boolean NOT NULL,
    compatibility_status text NOT NULL,

    cumulative_implied_inflow numeric,
    months_checked integer NOT NULL DEFAULT 0,
    months_complete integer NOT NULL DEFAULT 0,

    source_relation text NOT NULL,
    evidence_note text,

    calculated_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY(
        project_key,
        origin_period,
        target_period,
        scope_semantics
    ),

    CHECK(
        compatibility_status IN (
            'COMPATIBLE',
            'INCOMPATIBLE_INFLOW',
            'INSUFFICIENT_STOCK_FLOW_EVIDENCE',
            'INCOMPLETE_WINDOW'
        )
    )
);


-- ---------------------------------------------------------------
-- 6. Current derived monthly forecasts.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_monthly_current_v102 AS
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
    p.forecast_for_period,
    p.horizon_months,

    p.prediction,
    p.prediction_lower,
    p.prediction_upper,
    p.interval_level,

    p.naive_method,
    p.naive_prediction,

    p.evidence_class,
    p.prediction_status,
    p.maturity_date,

    p.lead_time_days,
    p.lead_time_months,
    p.lead_time_bucket,

    p.derivation_method,
    p.source_prediction_id,
    p.source_previous_prediction_id,
    p.source_horizon_months,

    p.scope_semantics,
    p.source_system,
    p.source_run_ref,
    p.source_model_ref,

    r.issued_at,
    r.data_cutoff_date,
    r.feature_version,
    r.dataset_snapshot_id,
    r.code_sha,

    (p.metadata->>'source_evidence_class') AS source_evidence_class,
    (p.metadata->>'interval_status') AS interval_status

FROM analytics.forecast_prediction_v1 p
JOIN model_control.forecast_run_v1 r
  ON r.run_id=p.run_id
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
WHERE
    p.derivation_method='CUMULATIVE_TO_MONTHLY_INCREMENT_V102'
    AND p.aggregation_semantics='PERIOD_VALUE'
    AND r.run_status='ISSUED';


-- ---------------------------------------------------------------
-- 7. Monthly maturity clock.
--
-- Important:
-- - Actual must be complete.
-- - Strict prospective evidence requires issuance BEFORE month start.
-- - Existing-stock scope must be proven compatible.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_monthly_maturity_clock_v102 AS
SELECT
    p.*,

    a.actual_id,
    a.actual_value,
    a.period_complete,
    a.period_closed_at,

    sc.compatible_scope,
    sc.compatibility_status,
    sc.cumulative_implied_inflow,

    CASE
        WHEN p.prediction_status='INVALIDATED'
            THEN 'INVALIDATED'

        WHEN a.actual_id IS NULL OR NOT a.period_complete
            THEN 'INCUBATING'

        WHEN p.scope_semantics='EXISTING_STOCK_NO_FUTURE_INFLOWS'
             AND coalesce(sc.compatible_scope,false)=false
            THEN 'BLOCKED_SCOPE'

        WHEN a.period_complete
            THEN 'MATURE'

        ELSE 'INCUBATING'
    END AS maturity_status,

    CASE
        WHEN p.evidence_class='PROSPECTIVE'
         AND p.issued_at < p.forecast_for_period::timestamptz
         AND p.data_cutoff_date < p.forecast_for_period
         AND a.period_closed_at IS NOT NULL
        THEN true
        ELSE false
    END AS strict_prospective_order_valid

FROM analytics.v_forecast_monthly_current_v102 p
LEFT JOIN analytics.forecast_actual_v1 a
  ON a.project_key=p.project_key
 AND a.target_name='sales_units'
 AND a.segment_key=p.segment_key
 AND a.actual_period=p.forecast_for_period
LEFT JOIN analytics.forecast_scope_compatibility_v102 sc
  ON sc.project_key=p.project_key
 AND sc.origin_period=p.origin_period
 AND sc.target_period=p.forecast_for_period
 AND sc.scope_semantics=p.scope_semantics;


-- ---------------------------------------------------------------
-- 8. Mature monthly pairs.
-- Intervals remain NULL for derived increments until calibrated
-- directly on prospective monthly residuals.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_monthly_mature_pairs_v102 AS
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

    (
        mc.evidence_class='PROSPECTIVE'
        AND mc.strict_prospective_order_valid
        AND mc.maturity_status='MATURE'
    ) AS leakage_safe

FROM analytics.v_forecast_monthly_maturity_clock_v102 mc
WHERE mc.maturity_status='MATURE';


-- ---------------------------------------------------------------
-- 9. Lead-time performance.
--
-- This is the main surface for asking:
-- "How good is the model when we ask it 20 / 45 / 75 days ahead?"
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_lead_time_performance_v102 AS
SELECT
    mp.run_id,
    mp.model_name,
    mp.model_version,
    mp.model_family,

    mp.project_key,
    mp.target_name,
    mp.segment_key,

    mp.lead_time_bucket,
    mp.lead_time_months,
    mp.evidence_class,

    count(*) AS mature_pairs,
    count(*) FILTER(WHERE mp.leakage_safe) AS leakage_safe_pairs,

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

    min(mp.forecast_for_period) AS first_mature_period,
    max(mp.forecast_for_period) AS latest_mature_period

FROM analytics.v_forecast_monthly_mature_pairs_v102 mp
GROUP BY
    mp.run_id, mp.model_name, mp.model_version, mp.model_family,
    mp.project_key, mp.target_name, mp.segment_key,
    mp.lead_time_bucket, mp.lead_time_months, mp.evidence_class;


-- ---------------------------------------------------------------
-- 10. Point forecast gate and uncertainty gate separated.
--
-- No model is punished for honest missing intervals during
-- incubation; but full defendability still requires uncertainty.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_lead_time_defendability_v102 AS
WITH policy AS (
    SELECT
        6::integer AS min_mature_pairs,
        0.25::numeric AS wape_threshold,
        0.0::numeric AS min_skill_vs_naive,
        0.60::numeric AS min_interval_coverage
)
SELECT
    perf.*,

    CASE
        WHEN perf.evidence_class <> 'PROSPECTIVE'
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
        ELSE 'PASS'
    END AS point_gate_status,

    CASE
        WHEN perf.interval_coverage IS NULL
            THEN 'INCUBATING'
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'WARN'
        ELSE 'PASS'
    END AS uncertainty_gate_status,

    CASE
        WHEN perf.evidence_class <> 'PROSPECTIVE'
            THEN 'BLOCK'
        WHEN perf.mature_pairs < p.min_mature_pairs
            THEN 'INCUBATING'
        WHEN perf.leakage_safe_pairs < perf.mature_pairs
            THEN 'BLOCK'
        WHEN perf.wape IS NULL OR perf.naive_wape IS NULL
            THEN 'BLOCK'
        WHEN perf.wape > p.wape_threshold
             OR perf.skill_vs_naive < p.min_skill_vs_naive
            THEN 'WARN'
        WHEN perf.interval_coverage IS NULL
            THEN 'POINT_PASS_INTERVAL_INCUBATING'
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'WARN'
        ELSE 'PASS'
    END AS overall_gate_status

FROM analytics.v_forecast_lead_time_performance_v102 perf
CROSS JOIN policy p;


-- ---------------------------------------------------------------
-- 11. Prospective issuance clock.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_issuance_clock_v102 AS
SELECT
    p.run_id,
    p.model_name,
    p.model_version,
    p.project_key,

    min(p.issued_at) AS issued_at,
    min(p.data_cutoff_date) AS data_cutoff_date,

    count(*) AS monthly_predictions,
    count(*) FILTER(WHERE p.evidence_class='PROSPECTIVE') AS prospective_predictions,
    count(*) FILTER(WHERE p.evidence_class='SHADOW') AS shadow_predictions,
    count(*) FILTER(WHERE p.evidence_class='BACKTEST') AS backtest_predictions,

    min(p.forecast_for_period)
        FILTER(WHERE p.evidence_class='PROSPECTIVE') AS first_prospective_period,

    min(p.maturity_date)
        FILTER(
            WHERE p.evidence_class='PROSPECTIVE'
              AND p.maturity_date >= current_date
        ) AS next_maturity_date,

    CASE
        WHEN count(*) FILTER(WHERE p.evidence_class='PROSPECTIVE') = 0
            THEN 'NO_PROSPECTIVE_EVIDENCE'
        WHEN count(*) FILTER(
            WHERE p.evidence_class='PROSPECTIVE'
              AND p.maturity_date >= current_date
        ) > 0
            THEN 'PROSPECTIVE_INCUBATING'
        ELSE 'PROSPECTIVE_MATURITY_AVAILABLE'
    END AS issuance_clock_status

FROM analytics.v_forecast_monthly_current_v102 p
GROUP BY
    p.run_id, p.model_name, p.model_version, p.project_key;


-- ---------------------------------------------------------------
-- 12. Power BI surfaces.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_forecast_monthly_current_v102 AS
SELECT *
FROM analytics.v_forecast_monthly_maturity_clock_v102;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_lead_time_performance_v102 AS
SELECT *
FROM analytics.v_forecast_lead_time_defendability_v102;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_issuance_clock_v102 AS
SELECT *
FROM analytics.v_forecast_issuance_clock_v102;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_adapter_audit_v102 AS
SELECT *
FROM model_control.forecast_adapter_audit_v102;


COMMENT ON VIEW analytics.v_forecast_issuance_clock_v102 IS
'Prospective issuance clock by model/run/project. Tracks future monthly forecasts and next maturity.';
COMMENT ON VIEW analytics.v_forecast_lead_time_performance_v102 IS
'Evaluates forecast quality by true lead time instead of only source cumulative horizon.';
COMMENT ON TABLE analytics.forecast_scope_compatibility_v102 IS
'Origin-dependent proof that observed monthly sales are comparable with existing-stock-only forecast scope.';

COMMIT;
