BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE TABLE IF NOT EXISTS analytics.project_ai_analysis_snapshot_v291 (
    analysis_snapshot_id bigserial PRIMARY KEY,
    analysis_hash text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),

    project_key text NOT NULL,
    project_name text,
    context_snapshot_id bigint,

    archetype text NOT NULL,
    priority_score numeric,
    evidence_level text,
    economic_signal text,
    predictive_state text,
    execution_state text,

    analysis_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(project_key, analysis_hash)
);

CREATE INDEX IF NOT EXISTS ix_project_ai_analysis_snapshot_v291_project_ts
ON analytics.project_ai_analysis_snapshot_v291(project_key, captured_at DESC);

CREATE OR REPLACE VIEW analytics.v_project_ai_analysis_latest_v291 AS
SELECT *
FROM (
    SELECT
        a.*,
        row_number() OVER (
            PARTITION BY project_key
            ORDER BY captured_at DESC, analysis_snapshot_id DESC
        ) AS rn
    FROM analytics.project_ai_analysis_snapshot_v291 a
) x
WHERE rn = 1;


CREATE TABLE IF NOT EXISTS decision_intelligence.project_decision_contract_draft_v291 (
    draft_id bigserial PRIMARY KEY,
    draft_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    project_key text NOT NULL,
    project_name text,
    context_snapshot_id bigint,

    archetype text NOT NULL,
    priority_score numeric,
    contract_type text NOT NULL,

    hypothesis text,
    proposed_action text,
    owner_suggested text,

    deadline date,
    primary_metric text,
    secondary_metrics jsonb,
    baseline_json jsonb,
    success_criterion text,

    value_at_risk numeric,
    value_to_capture numeric,
    action_cost numeric,
    expected_roi numeric,

    evidence_level text,
    evidence_gaps jsonb,
    required_before_execution jsonb,

    status text NOT NULL DEFAULT 'DRAFT_REVIEW_REQUIRED',
    approved_at timestamptz,
    approved_by text,

    UNIQUE(project_key, draft_hash)
);

CREATE INDEX IF NOT EXISTS ix_project_decision_contract_draft_v291_status
ON decision_intelligence.project_decision_contract_draft_v291(status, priority_score DESC);

CREATE OR REPLACE VIEW decision_intelligence.v_decision_contract_review_queue_v291 AS
SELECT
    draft_id,
    project_key,
    project_name,
    archetype,
    priority_score,
    contract_type,
    hypothesis,
    proposed_action,
    owner_suggested,
    deadline,
    primary_metric,
    value_at_risk,
    evidence_level,
    status,
    created_at
FROM decision_intelligence.project_decision_contract_draft_v291
WHERE status = 'DRAFT_REVIEW_REQUIRED'
ORDER BY priority_score DESC NULLS LAST, created_at DESC;


CREATE OR REPLACE VIEW analytics.v_active_portfolio_priority_v291 AS
SELECT
    a.project_key,
    a.project_name,
    a.archetype,
    a.priority_score,
    a.evidence_level,
    a.economic_signal,
    a.predictive_state,
    a.execution_state,
    d.contract_type,
    d.owner_suggested,
    d.deadline,
    d.primary_metric,
    d.status AS contract_status,
    a.captured_at
FROM analytics.v_project_ai_analysis_latest_v291 a
LEFT JOIN LATERAL (
    SELECT d.*
    FROM decision_intelligence.project_decision_contract_draft_v291 d
    WHERE d.project_key = a.project_key
    ORDER BY d.created_at DESC, d.draft_id DESC
    LIMIT 1
) d ON TRUE
ORDER BY a.priority_score DESC NULLS LAST, a.project_key;

COMMENT ON TABLE decision_intelligence.project_decision_contract_draft_v291 IS
'AI-assisted draft only. Never execute automatically. Deadline, action cost, success threshold, ROI and causal claim require human/evidence review.';

COMMIT;
