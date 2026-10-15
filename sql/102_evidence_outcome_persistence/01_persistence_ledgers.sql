BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS experiments;
CREATE SCHEMA IF NOT EXISTS model_control;

-- IMPORTANT:
-- This migration deliberately DOES NOT create/replace analytics.v_project_growth_state.
-- v2.7.2 owns that governed business view.
-- The persistence layer gets its own snapshot-current view instead.

CREATE TABLE IF NOT EXISTS analytics.project_growth_state_snapshot (
    snapshot_id bigserial PRIMARY KEY,
    snapshot_ts timestamptz NOT NULL,
    slot text,
    project_key text NOT NULL,
    project_name text,
    source_artifact text,
    stock_units numeric,
    stock_value numeric,
    sales_units numeric,
    sales_value numeric,
    absorption_rate numeric,
    months_to_zero numeric,
    avg_price_m2 numeric,
    forecast_units numeric,
    forecast_wape_pct numeric,
    target_value numeric,
    gap_value numeric,
    value_to_capture numeric,
    action_cost numeric,
    uplift_pct numeric,
    confidence numeric,
    expected_roi numeric,
    trust_score_pct numeric,
    evidence_grade text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_project_growth_state_snapshot_project_ts
ON analytics.project_growth_state_snapshot(project_key, snapshot_ts DESC);

CREATE OR REPLACE VIEW analytics.v_project_growth_state_snapshot_current AS
SELECT *
FROM (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY project_key
            ORDER BY snapshot_ts DESC, snapshot_id DESC
        ) AS rn
    FROM analytics.project_growth_state_snapshot s
) x
WHERE rn = 1;

CREATE TABLE IF NOT EXISTS model_control.evidence_gate (
    gate_id text PRIMARY KEY,
    run_id text,
    gate_ts timestamptz NOT NULL,
    slot text,
    claim_level text NOT NULL,
    gate_name text NOT NULL,
    gate_status text NOT NULL,
    evidence_grade text,
    score numeric,
    threshold numeric,
    reason text,
    missing_evidence text,
    source_artifact text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_evidence_gate_level_ts
ON model_control.evidence_gate(claim_level, gate_ts DESC);

CREATE OR REPLACE VIEW model_control.v_evidence_gate_current AS
SELECT *
FROM (
    SELECT
        eg.*,
        row_number() OVER (
            PARTITION BY claim_level
            ORDER BY gate_ts DESC, created_at DESC
        ) AS rn
    FROM model_control.evidence_gate eg
) x
WHERE rn = 1;

CREATE TABLE IF NOT EXISTS decision_intelligence.decision_ledger (
    decision_id text PRIMARY KEY,
    run_id text,
    decision_ts timestamptz NOT NULL,
    slot text,
    project_key text,
    challenge text,
    decision_title text NOT NULL,
    decision_rationale text,
    owner text,
    deadline date,
    decision_status text NOT NULL DEFAULT 'PROPOSED',
    decision_level text NOT NULL DEFAULT 'D1_RECOMMEND',
    evidence_grade text,
    gate_status text,
    value_at_risk numeric,
    economic_exposure numeric,
    value_to_capture numeric,
    action_cost numeric,
    confidence numeric,
    expected_roi numeric,
    confidence_adjusted_value numeric,
    quantification_status text,
    missing_evidence text,
    source_artifact text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_decision_ledger_project_status
ON decision_intelligence.decision_ledger(project_key, decision_status);

CREATE TABLE IF NOT EXISTS decision_intelligence.action_log (
    action_id text PRIMARY KEY,
    decision_id text NOT NULL
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE CASCADE,
    action_ts timestamptz NOT NULL DEFAULT now(),
    actor text,
    action_type text,
    action_description text,
    action_status text NOT NULL DEFAULT 'OPEN',
    expected_completion_at timestamptz,
    completed_at timestamptz,
    action_cost_realized numeric,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_action_log_decision_status
ON decision_intelligence.action_log(decision_id, action_status);

CREATE TABLE IF NOT EXISTS decision_intelligence.outcome_ledger (
    outcome_id text PRIMARY KEY,
    decision_id text NOT NULL
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE CASCADE,
    outcome_ts timestamptz NOT NULL DEFAULT now(),
    metric_name text NOT NULL,
    baseline_value numeric,
    observed_value numeric,
    incremental_value numeric,
    value_realized numeric,
    confidence numeric,
    maturity_status text NOT NULL DEFAULT 'IMMATURE',
    attribution_method text,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_outcome_ledger_decision_ts
ON decision_intelligence.outcome_ledger(decision_id, outcome_ts DESC);

CREATE TABLE IF NOT EXISTS experiments.baseline_challenger (
    experiment_id text PRIMARY KEY,
    decision_id text
        REFERENCES decision_intelligence.decision_ledger(decision_id)
        ON DELETE SET NULL,
    project_key text,
    treatment_name text,
    control_name text,
    metric_name text,
    hypothesis text,
    start_date date,
    end_date date,
    baseline_value numeric,
    treatment_value numeric,
    control_value numeric,
    uplift_estimate numeric,
    p_value numeric,
    confidence_interval_low numeric,
    confidence_interval_high numeric,
    value_realized numeric,
    experiment_status text NOT NULL DEFAULT 'PLANNED',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_baseline_challenger_project_status
ON experiments.baseline_challenger(project_key, experiment_status);

CREATE OR REPLACE VIEW decision_intelligence.v_decision_outcome_status AS
SELECT
    d.decision_id,
    d.run_id,
    d.decision_ts,
    d.project_key,
    d.challenge,
    d.decision_title,
    d.owner,
    d.decision_status,
    d.decision_level,
    d.quantification_status,
    d.value_at_risk,
    d.value_to_capture,
    d.action_cost,
    d.confidence,
    d.expected_roi,
    d.confidence_adjusted_value,
    count(DISTINCT a.action_id) AS action_count,
    count(DISTINCT o.outcome_id) AS outcome_count,
    max(o.outcome_ts) AS latest_outcome_ts,
    sum(o.value_realized) AS value_realized_total,
    CASE
        WHEN count(DISTINCT o.outcome_id) = 0 THEN 'NO_OUTCOME'
        WHEN bool_or(o.maturity_status = 'MATURE') THEN 'MATURE_OUTCOME'
        ELSE 'IMMATURE_OUTCOME'
    END AS outcome_status
FROM decision_intelligence.decision_ledger d
LEFT JOIN decision_intelligence.action_log a
    ON a.decision_id = d.decision_id
LEFT JOIN decision_intelligence.outcome_ledger o
    ON o.decision_id = d.decision_id
GROUP BY
    d.decision_id, d.run_id, d.decision_ts, d.project_key, d.challenge,
    d.decision_title, d.owner, d.decision_status, d.decision_level,
    d.quantification_status, d.value_at_risk, d.value_to_capture,
    d.action_cost, d.confidence, d.expected_roi, d.confidence_adjusted_value;

COMMIT;
