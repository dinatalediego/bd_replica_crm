BEGIN;

CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

-- ===============================================================
-- Medallio Forecast Factory Contract v1
-- ===============================================================

CREATE TABLE IF NOT EXISTS model_control.forecast_model_registry_v1 (
    model_version_id bigserial PRIMARY KEY,
    model_name text NOT NULL,
    model_version text NOT NULL,
    model_family text NOT NULL,
    target_name text NOT NULL,
    owner text NOT NULL,
    lifecycle_status text NOT NULL DEFAULT 'DEVELOPMENT',
    repo_reference text,
    code_sha text,
    artifact_reference text,
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(model_name, model_version, target_name),
    CHECK (lifecycle_status IN ('DEVELOPMENT','CHALLENGER','CHAMPION','RETIRED'))
);


CREATE TABLE IF NOT EXISTS model_control.forecast_run_v1 (
    run_id bigserial PRIMARY KEY,
    model_version_id bigint NOT NULL
        REFERENCES model_control.forecast_model_registry_v1(model_version_id),

    issued_at timestamptz NOT NULL,
    data_cutoff_date date NOT NULL,

    training_start_date date NOT NULL,
    training_end_date date NOT NULL,

    feature_version text NOT NULL,
    dataset_snapshot_id text NOT NULL,
    code_sha text NOT NULL,

    run_status text NOT NULL DEFAULT 'ISSUED',
    run_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    environment_fingerprint jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes text,

    created_at timestamptz NOT NULL DEFAULT now(),

    CHECK (run_status IN ('ISSUED','INVALIDATED','RETIRED')),
    CHECK (training_start_date <= training_end_date),
    CHECK (training_end_date <= data_cutoff_date)
);

CREATE INDEX IF NOT EXISTS ix_forecast_run_v1_model_issued
ON model_control.forecast_run_v1(model_version_id, issued_at DESC);


CREATE TABLE IF NOT EXISTS analytics.forecast_prediction_v1 (
    prediction_id bigserial PRIMARY KEY,
    run_id bigint NOT NULL
        REFERENCES model_control.forecast_run_v1(run_id),

    project_key text NOT NULL,
    target_name text NOT NULL,
    target_unit text NOT NULL,
    segment_key text NOT NULL DEFAULT 'ALL',

    forecast_for_period date NOT NULL,
    horizon_months integer NOT NULL,

    prediction numeric NOT NULL,
    prediction_lower numeric NOT NULL,
    prediction_upper numeric NOT NULL,
    interval_level numeric NOT NULL DEFAULT 0.80,

    naive_method text NOT NULL,
    naive_prediction numeric NOT NULL,

    evidence_class text NOT NULL,
    prediction_status text NOT NULL DEFAULT 'ISSUED',

    maturity_date date,
    issued_at_copy timestamptz NOT NULL,
    data_cutoff_date_copy date NOT NULL,

    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (
        run_id, project_key, target_name, segment_key,
        forecast_for_period, horizon_months
    ),

    CHECK (horizon_months >= 1),
    CHECK (prediction_lower <= prediction),
    CHECK (prediction <= prediction_upper),
    CHECK (interval_level > 0 AND interval_level < 1),
    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST')),
    CHECK (prediction_status IN ('ISSUED','INCUBATING','MATURE','EVALUATED','INVALIDATED'))
);

CREATE INDEX IF NOT EXISTS ix_forecast_prediction_v1_project_period
ON analytics.forecast_prediction_v1(
    project_key, target_name, segment_key, forecast_for_period, horizon_months
);

CREATE INDEX IF NOT EXISTS ix_forecast_prediction_v1_maturity
ON analytics.forecast_prediction_v1(prediction_status, maturity_date);


CREATE TABLE IF NOT EXISTS analytics.forecast_actual_v1 (
    actual_id bigserial PRIMARY KEY,

    project_key text NOT NULL,
    target_name text NOT NULL,
    target_unit text NOT NULL,
    segment_key text NOT NULL DEFAULT 'ALL',
    actual_period date NOT NULL,

    actual_value numeric NOT NULL,

    period_complete boolean NOT NULL DEFAULT false,
    period_closed_at timestamptz,

    source_relation text NOT NULL,
    source_reference text,
    source_snapshot_id text,

    loaded_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(project_key, target_name, segment_key, actual_period)
);

CREATE INDEX IF NOT EXISTS ix_forecast_actual_v1_lookup
ON analytics.forecast_actual_v1(project_key, target_name, segment_key, actual_period);


CREATE TABLE IF NOT EXISTS analytics.forecast_evaluation_v1 (
    evaluation_id bigserial PRIMARY KEY,
    prediction_id bigint NOT NULL UNIQUE
        REFERENCES analytics.forecast_prediction_v1(prediction_id),
    actual_id bigint NOT NULL
        REFERENCES analytics.forecast_actual_v1(actual_id),

    evaluated_at timestamptz NOT NULL DEFAULT now(),

    actual_value numeric NOT NULL,
    prediction numeric NOT NULL,
    naive_prediction numeric NOT NULL,

    signed_error numeric NOT NULL,
    absolute_error numeric NOT NULL,
    ape numeric,

    naive_signed_error numeric NOT NULL,
    naive_absolute_error numeric NOT NULL,
    naive_ape numeric,

    interval_hit boolean NOT NULL,
    interval_width numeric NOT NULL,

    evidence_class text NOT NULL,
    leakage_safe boolean NOT NULL,

    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,

    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST'))
);

CREATE INDEX IF NOT EXISTS ix_forecast_evaluation_v1_class
ON analytics.forecast_evaluation_v1(evidence_class, evaluated_at DESC);


CREATE TABLE IF NOT EXISTS model_control.forecast_evidence_v1 (
    evidence_id bigserial PRIMARY KEY,
    run_id bigint
        REFERENCES model_control.forecast_run_v1(run_id),
    prediction_id bigint
        REFERENCES analytics.forecast_prediction_v1(prediction_id),

    evidence_type text NOT NULL,
    evidence_class text NOT NULL,

    source_reference text NOT NULL,
    evidence_hash text,

    verification_status text NOT NULL DEFAULT 'UNVERIFIED',
    verified_at timestamptz,
    verified_by text,

    evidence_note text,
    created_at timestamptz NOT NULL DEFAULT now(),

    CHECK (evidence_class IN ('PROSPECTIVE','BACKTEST','GOVERNANCE')),
    CHECK (verification_status IN ('UNVERIFIED','VERIFIED','REJECTED'))
);


CREATE TABLE IF NOT EXISTS model_control.forecast_gate_policy_v1 (
    policy_id bigserial PRIMARY KEY,
    policy_name text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true,

    wape_threshold numeric NOT NULL DEFAULT 0.25,
    min_mature_pairs integer NOT NULL DEFAULT 6,
    min_skill_vs_naive numeric NOT NULL DEFAULT 0.0,
    min_interval_coverage numeric NOT NULL DEFAULT 0.60,
    prospective_only boolean NOT NULL DEFAULT true,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO model_control.forecast_gate_policy_v1(
    policy_name, is_active, wape_threshold, min_mature_pairs,
    min_skill_vs_naive, min_interval_coverage, prospective_only
)
VALUES('CEO_DEFAULT', true, 0.25, 6, 0.0, 0.60, true)
ON CONFLICT(policy_name) DO NOTHING;


-- ===============================================================
-- Contract compliance
-- ===============================================================

CREATE OR REPLACE VIEW model_control.v_forecast_run_contract_compliance_v1 AS
SELECT
    r.run_id,
    r.model_version_id,
    mr.model_name,
    mr.model_version,
    mr.target_name AS registry_target_name,
    r.issued_at,
    r.data_cutoff_date,

    count(p.prediction_id) AS prediction_rows,

    bool_and(p.prediction_lower IS NOT NULL) AS has_lower_interval,
    bool_and(p.prediction_upper IS NOT NULL) AS has_upper_interval,
    bool_and(p.naive_method IS NOT NULL AND btrim(p.naive_method) <> '') AS has_naive_method,
    bool_and(p.naive_prediction IS NOT NULL) AS has_naive_prediction,
    bool_and(p.horizon_months >= 1) AS horizons_valid,

    bool_and(
        CASE
            WHEN p.evidence_class='PROSPECTIVE'
            THEN p.data_cutoff_date_copy < p.forecast_for_period
                 AND p.issued_at_copy <= p.created_at
            ELSE true
        END
    ) AS prospective_temporal_order_valid,

    CASE
        WHEN count(p.prediction_id)=0 THEN 'NO_PREDICTIONS'
        WHEN NOT bool_and(p.prediction_lower IS NOT NULL) THEN 'MISSING_INTERVAL'
        WHEN NOT bool_and(p.prediction_upper IS NOT NULL) THEN 'MISSING_INTERVAL'
        WHEN NOT bool_and(p.naive_method IS NOT NULL AND btrim(p.naive_method) <> '') THEN 'MISSING_NAIVE'
        WHEN NOT bool_and(p.naive_prediction IS NOT NULL) THEN 'MISSING_NAIVE'
        WHEN NOT bool_and(p.horizon_months >= 1) THEN 'INVALID_HORIZON'
        WHEN NOT bool_and(
            CASE
                WHEN p.evidence_class='PROSPECTIVE'
                THEN p.data_cutoff_date_copy < p.forecast_for_period
                ELSE true
            END
        ) THEN 'TEMPORAL_LEAKAGE_RISK'
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


-- ===============================================================
-- Maturity clock
-- A monthly forecast becomes eligible only when the actual period
-- is explicitly marked complete.
-- ===============================================================

CREATE OR REPLACE VIEW analytics.v_forecast_maturity_clock_v1 AS
SELECT
    p.prediction_id,
    p.run_id,
    p.project_key,
    p.target_name,
    p.target_unit,
    p.segment_key,
    p.forecast_for_period,
    p.horizon_months,
    p.evidence_class,

    p.prediction,
    p.prediction_lower,
    p.prediction_upper,
    p.naive_method,
    p.naive_prediction,

    p.issued_at_copy AS issued_at,
    p.data_cutoff_date_copy AS data_cutoff_date,

    a.actual_id,
    a.actual_value,
    a.period_complete,
    a.period_closed_at,

    CASE
        WHEN p.prediction_status='INVALIDATED' THEN 'INVALIDATED'
        WHEN a.actual_id IS NULL THEN 'INCUBATING'
        WHEN NOT a.period_complete THEN 'INCUBATING'
        WHEN a.period_complete THEN 'MATURE'
        ELSE 'INCUBATING'
    END AS maturity_status

FROM analytics.forecast_prediction_v1 p
LEFT JOIN analytics.forecast_actual_v1 a
  ON a.project_key=p.project_key
 AND a.target_name=p.target_name
 AND a.segment_key=p.segment_key
 AND a.actual_period=p.forecast_for_period;


-- ===============================================================
-- Row-level mature evaluation
-- ===============================================================

CREATE OR REPLACE VIEW analytics.v_forecast_mature_pairs_v1 AS
SELECT
    mc.prediction_id,
    mc.run_id,
    mc.project_key,
    mc.target_name,
    mc.target_unit,
    mc.segment_key,
    mc.forecast_for_period,
    mc.horizon_months,
    mc.evidence_class,

    mc.prediction,
    mc.prediction_lower,
    mc.prediction_upper,
    mc.naive_method,
    mc.naive_prediction,
    mc.actual_id,
    mc.actual_value,

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

    (mc.actual_value BETWEEN mc.prediction_lower AND mc.prediction_upper) AS interval_hit,
    (mc.prediction_upper - mc.prediction_lower) AS interval_width,

    (
        mc.evidence_class='PROSPECTIVE'
        AND mc.data_cutoff_date < mc.forecast_for_period
        AND mc.issued_at < mc.period_closed_at
    ) AS leakage_safe

FROM analytics.v_forecast_maturity_clock_v1 mc
WHERE mc.maturity_status='MATURE';


-- ===============================================================
-- Performance summary:
-- one stable surface for model selection + Power BI.
-- ===============================================================

CREATE OR REPLACE VIEW analytics.v_forecast_performance_v1 AS
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
        (
            sum(mp.absolute_error)
            / nullif(sum(abs(mp.actual_value)),0)
        )
        /
        nullif(
            (
                sum(mp.naive_absolute_error)
                / nullif(sum(abs(mp.actual_value)),0)
            ), 0
        )
    ) AS skill_vs_naive,

    avg(CASE WHEN mp.interval_hit THEN 1.0 ELSE 0.0 END) AS interval_coverage,

    avg(mp.interval_width) AS avg_interval_width,

    min(mp.forecast_for_period) AS first_mature_period,
    max(mp.forecast_for_period) AS latest_mature_period

FROM analytics.v_forecast_mature_pairs_v1 mp
JOIN model_control.forecast_run_v1 r
  ON r.run_id=mp.run_id
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
GROUP BY
    mp.run_id, r.model_version_id, mr.model_name, mr.model_version,
    mr.model_family, mp.project_key, mp.target_name, mp.target_unit,
    mp.segment_key, mp.horizon_months, mp.evidence_class;


-- ===============================================================
-- CEO defendability gate
-- ===============================================================

CREATE OR REPLACE VIEW analytics.v_forecast_defendability_v1 AS
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
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'WARN'
        ELSE 'PASS'
    END AS defendability_status,

    CASE
        WHEN p.prospective_only AND perf.evidence_class <> 'PROSPECTIVE'
            THEN 'Evidence is backtest-only.'
        WHEN perf.mature_pairs < p.min_mature_pairs
            THEN 'Not enough mature prospective pairs.'
        WHEN perf.leakage_safe_pairs < perf.mature_pairs
            THEN 'At least one mature pair fails leakage-safety checks.'
        WHEN perf.wape > p.wape_threshold
            THEN 'WAPE is above policy threshold.'
        WHEN perf.skill_vs_naive < p.min_skill_vs_naive
            THEN 'Model does not beat the naive benchmark.'
        WHEN perf.interval_coverage < p.min_interval_coverage
            THEN 'Prediction interval coverage is below policy threshold.'
        ELSE 'Forecast evidence satisfies the active policy.'
    END AS defendability_reason

FROM analytics.v_forecast_performance_v1 perf
CROSS JOIN policy p;


-- ===============================================================
-- Power BI stable semantic surfaces
-- ===============================================================

CREATE OR REPLACE VIEW analytics.v_pbi_forecast_factory_current_v1 AS
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

    r.issued_at,
    r.data_cutoff_date,
    r.feature_version,
    r.dataset_snapshot_id,
    r.code_sha,

    mc.maturity_status,
    mc.actual_value,
    mc.period_closed_at

FROM analytics.forecast_prediction_v1 p
JOIN model_control.forecast_run_v1 r
  ON r.run_id=p.run_id
JOIN model_control.forecast_model_registry_v1 mr
  ON mr.model_version_id=r.model_version_id
LEFT JOIN analytics.v_forecast_maturity_clock_v1 mc
  ON mc.prediction_id=p.prediction_id
WHERE r.run_status='ISSUED';


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_performance_v1 AS
SELECT
    d.*,
    rc.contract_status AS run_contract_status
FROM analytics.v_forecast_defendability_v1 d
LEFT JOIN model_control.v_forecast_run_contract_compliance_v1 rc
  ON rc.run_id=d.run_id;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_evidence_v1 AS
SELECT
    e.evidence_id,
    e.run_id,
    e.prediction_id,
    e.evidence_type,
    e.evidence_class,
    e.source_reference,
    e.verification_status,
    e.verified_at,
    e.verified_by,
    e.evidence_note,
    e.created_at
FROM model_control.forecast_evidence_v1 e;


COMMENT ON TABLE analytics.forecast_prediction_v1 IS
'Canonical model-agnostic forecast output. Any future model must write this contract.';
COMMENT ON VIEW analytics.v_pbi_forecast_factory_current_v1 IS
'Stable Power BI interface for all future forecasting models.';
COMMENT ON VIEW analytics.v_pbi_forecast_performance_v1 IS
'Stable Power BI interface for mature accuracy, naive benchmark skill and defendability.';

COMMIT;
