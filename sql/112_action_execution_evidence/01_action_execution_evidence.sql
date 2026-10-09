BEGIN;

CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ===============================================================
-- Medallio v2.9.3 — Action Execution Evidence + Intervention Ledger
-- ===============================================================

CREATE TABLE IF NOT EXISTS decision_intelligence.intervention_ledger_v293 (
    intervention_id bigserial PRIMARY KEY,
    intervention_code text NOT NULL UNIQUE,

    contract_id bigint NOT NULL UNIQUE,
    contract_code text NOT NULL,
    project_key text NOT NULL,
    project_name text,

    approved_action text,
    owner text NOT NULL,

    planned_start_date date,
    actual_start_date date,
    actual_end_date date,

    execution_status text NOT NULL DEFAULT 'SCHEDULED',

    planned_scope jsonb,
    current_scope jsonb,

    planned_action_cost numeric,
    actual_action_cost numeric NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'PEN',

    evidence_count integer NOT NULL DEFAULT 0,
    material_change_count integer NOT NULL DEFAULT 0,

    last_event_at timestamptz,
    last_event_type text,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CHECK (
        execution_status IN (
            'SCHEDULED','STARTED','IMPLEMENTED','COMPLETED','CANCELLED'
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_intervention_ledger_v293_project
ON decision_intelligence.intervention_ledger_v293(project_key, updated_at DESC);


CREATE TABLE IF NOT EXISTS decision_intelligence.intervention_event_v293 (
    intervention_event_id bigserial PRIMARY KEY,
    intervention_id bigint NOT NULL,
    contract_id bigint NOT NULL,
    project_key text NOT NULL,

    event_type text NOT NULL,
    event_ts timestamptz NOT NULL DEFAULT now(),
    effective_date date,

    actor text NOT NULL,
    note text,

    before_state jsonb,
    after_state jsonb,
    event_payload jsonb,

    is_material_change boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_intervention_event_v293_timeline
ON decision_intelligence.intervention_event_v293(intervention_id, event_ts);


CREATE TABLE IF NOT EXISTS decision_intelligence.intervention_cost_v293 (
    intervention_cost_id bigserial PRIMARY KEY,
    intervention_id bigint NOT NULL,
    contract_id bigint NOT NULL,
    project_key text NOT NULL,

    cost_date date NOT NULL,
    cost_category text NOT NULL,
    amount numeric NOT NULL CHECK(amount >= 0),
    currency text NOT NULL DEFAULT 'PEN',

    is_actual boolean NOT NULL DEFAULT true,
    source_reference text,
    note text,
    recorded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_intervention_cost_v293_intervention
ON decision_intelligence.intervention_cost_v293(intervention_id, cost_date);


CREATE TABLE IF NOT EXISTS decision_intelligence.intervention_evidence_v293 (
    evidence_id bigserial PRIMARY KEY,
    intervention_id bigint NOT NULL,
    contract_id bigint NOT NULL,
    project_key text NOT NULL,

    evidence_type text NOT NULL,
    evidence_ts timestamptz NOT NULL DEFAULT now(),
    source_reference text NOT NULL,
    evidence_note text,
    evidence_hash text,

    recorded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_intervention_evidence_v293_intervention
ON decision_intelligence.intervention_evidence_v293(intervention_id, evidence_ts DESC);


-- ----------------------------------------------------------------
-- Bootstrap helper: active human-approved contracts become SCHEDULED,
-- never STARTED automatically.
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION decision_intelligence.bootstrap_active_interventions_v293()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    inserted_count integer;
BEGIN
    INSERT INTO decision_intelligence.intervention_ledger_v293(
        intervention_code,
        contract_id,
        contract_code,
        project_key,
        project_name,
        approved_action,
        owner,
        planned_start_date,
        execution_status,
        planned_scope,
        current_scope,
        planned_action_cost,
        currency
    )
    SELECT
        'INT-' || c.contract_code,
        c.contract_id,
        c.contract_code,
        c.project_key,
        c.project_name,
        c.proposed_action,
        c.owner,
        NULL,
        'SCHEDULED',
        jsonb_build_object(
            'hypothesis', c.hypothesis,
            'primary_metric', c.primary_metric,
            'secondary_metrics', c.secondary_metrics,
            'deadline', c.deadline,
            'outcome_due_date', c.outcome_due_date
        ),
        jsonb_build_object(
            'hypothesis', c.hypothesis,
            'primary_metric', c.primary_metric,
            'secondary_metrics', c.secondary_metrics,
            'deadline', c.deadline,
            'outcome_due_date', c.outcome_due_date
        ),
        c.action_cost,
        c.currency
    FROM decision_intelligence.project_active_contract_v292 c
    WHERE c.project_key IN ('MD','MT')
      AND c.status IN ('ACTIVE','WAITING_OUTCOME','OUTCOME_MATURE')
      AND NOT EXISTS (
        SELECT 1
        FROM decision_intelligence.intervention_ledger_v293 i
        WHERE i.contract_id = c.contract_id
      );

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$;


-- ----------------------------------------------------------------
-- Monitoring views
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW decision_intelligence.v_intervention_event_timeline_v293 AS
SELECT
    i.intervention_code,
    i.contract_code,
    i.project_key,
    i.project_name,
    e.intervention_event_id,
    e.event_type,
    e.event_ts,
    e.effective_date,
    e.actor,
    e.note,
    e.is_material_change,
    e.event_payload
FROM decision_intelligence.intervention_ledger_v293 i
JOIN decision_intelligence.intervention_event_v293 e
  ON e.intervention_id = i.intervention_id
ORDER BY i.project_key, e.event_ts, e.intervention_event_id;


CREATE OR REPLACE VIEW decision_intelligence.v_intervention_monitoring_v293 AS
SELECT
    i.intervention_id,
    i.intervention_code,
    i.contract_id,
    i.contract_code,
    i.project_key,
    i.project_name,

    i.execution_status,
    i.owner,
    i.approved_action,

    c.deadline AS contract_deadline,
    i.planned_start_date,
    i.actual_start_date,
    i.actual_end_date,

    c.primary_metric,
    c.success_criterion,
    c.outcome_due_date,
    c.status AS contract_status,

    i.planned_action_cost,
    i.actual_action_cost,
    i.currency,

    i.evidence_count,
    i.material_change_count,
    i.last_event_at,
    i.last_event_type,

    (c.deadline - current_date) AS days_to_contract_deadline,
    (c.outcome_due_date - current_date) AS days_to_outcome_due,

    CASE
        WHEN i.execution_status='CANCELLED' THEN 'CANCELLED'
        WHEN i.execution_status='COMPLETED' THEN 'WAITING_OUTCOME'
        WHEN current_date > c.deadline
             AND i.execution_status IN ('SCHEDULED','STARTED')
            THEN 'EXECUTION_AT_RISK'
        WHEN i.execution_status='SCHEDULED' THEN 'READY_TO_START'
        WHEN i.execution_status='STARTED' THEN 'IN_EXECUTION'
        WHEN i.execution_status='IMPLEMENTED' THEN 'IMPLEMENTED_NOT_CLOSED'
        ELSE i.execution_status
    END AS execution_health,

    s.sla_status AS outcome_sla_status,
    s.outcome_count,
    s.mature_outcome_count,
    s.latest_outcome_at,
    s.latest_outcome_value,
    s.latest_value_realized

FROM decision_intelligence.intervention_ledger_v293 i
JOIN decision_intelligence.project_active_contract_v292 c
  ON c.contract_id=i.contract_id
LEFT JOIN decision_intelligence.v_outcome_sla_v292 s
  ON s.contract_id=i.contract_id;


CREATE OR REPLACE VIEW decision_intelligence.v_intervention_cost_summary_v293 AS
SELECT
    i.intervention_id,
    i.intervention_code,
    i.project_key,
    i.contract_code,
    coalesce(sum(c.amount) FILTER (WHERE c.is_actual), 0) AS actual_cost,
    coalesce(sum(c.amount) FILTER (WHERE NOT c.is_actual), 0) AS planned_cost_logged,
    count(c.intervention_cost_id) AS cost_records
FROM decision_intelligence.intervention_ledger_v293 i
LEFT JOIN decision_intelligence.intervention_cost_v293 c
  ON c.intervention_id=i.intervention_id
GROUP BY
    i.intervention_id, i.intervention_code, i.project_key, i.contract_code;


-- ----------------------------------------------------------------
-- Power BI / Python semantic views
-- Keep them intentionally flat and stable.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_ai_control_tower_v293 AS
SELECT
    cc.project_key,
    cc.project_name,
    cc.route_status,
    cc.activation_eligible,
    cc.workflow_status,
    cc.priority_score,
    cc.archetype,
    cc.contract_type,

    m.preliminary_delivery_date,
    m.days_to_preliminary_delivery,
    m.schedule_band,
    m.milestone_status_review_required,

    im.intervention_code,
    im.execution_status,
    im.execution_health,
    im.owner,
    im.contract_deadline,
    im.actual_start_date,
    im.actual_end_date,
    im.primary_metric,
    im.outcome_due_date,
    im.days_to_outcome_due,
    im.outcome_sla_status,
    im.outcome_count,
    im.mature_outcome_count,
    im.actual_action_cost,
    im.currency,

    ctx.highest_claim_level AS evidence_level,
    ctx.context_completeness_pct,

    CASE
        WHEN cc.route_status='BLOCKED_RECONCILIATION' THEN 'FIX DATA'
        WHEN cc.route_status='DESIGN_ONLY' THEN 'DESIGN'
        WHEN cc.route_status='EVIDENCE_BUILDING' THEN 'BUILD EVIDENCE'
        WHEN im.execution_health='EXECUTION_AT_RISK' THEN 'ESCALATE EXECUTION'
        WHEN im.execution_status='SCHEDULED' THEN 'START ACTION'
        WHEN im.execution_status IN ('STARTED','IMPLEMENTED') THEN 'MONITOR EXECUTION'
        WHEN im.execution_status='COMPLETED' THEN 'WAIT OUTCOME'
        WHEN cc.route_status='ACTIVATION_CANDIDATE' THEN 'REVIEW CONTRACT'
        ELSE 'MONITOR'
    END AS what_needs_me_now

FROM analytics.v_contract_command_center_v292 cc
LEFT JOIN analytics.v_project_schedule_context_v2921 m
  ON m.project_key=cc.project_key
LEFT JOIN decision_intelligence.v_intervention_monitoring_v293 im
  ON im.project_key=cc.project_key
LEFT JOIN analytics.v_project_context_latest_v290 ctx
  ON ctx.project_key=cc.project_key;


CREATE OR REPLACE VIEW analytics.v_pbi_outcome_roi_v293 AS
SELECT
    im.project_key,
    im.project_name,
    im.contract_code,
    im.intervention_code,
    im.primary_metric,
    im.execution_status,
    im.execution_health,
    im.outcome_due_date,
    im.outcome_sla_status,
    im.outcome_count,
    im.mature_outcome_count,
    im.latest_outcome_at,
    im.latest_outcome_value,
    im.latest_value_realized,

    im.planned_action_cost,
    im.actual_action_cost,

    CASE
        WHEN im.latest_value_realized IS NOT NULL
        THEN im.latest_value_realized - im.actual_action_cost
        ELSE NULL
    END AS observed_net_value,

    CASE
        WHEN im.latest_value_realized IS NOT NULL
             AND im.actual_action_cost > 0
        THEN (
            im.latest_value_realized - im.actual_action_cost
        ) / im.actual_action_cost
        ELSE NULL
    END AS observed_roi,

    'OBSERVED_ASSOCIATION_NOT_CAUSAL_PROOF'::text AS roi_interpretation

FROM decision_intelligence.v_intervention_monitoring_v293 im;


CREATE OR REPLACE VIEW analytics.v_pbi_project_deep_dive_v293 AS
SELECT
    g.project_key,
    g.project_name,
    g.snapshot_date,
    g.latest_complete_period,
    g.stock_units,
    g.sales_units,
    g.ventas_promedio_3m,
    g.ventas_promedio_6m,
    g.absorcion_promedio_3m,
    g.absorcion_promedio_6m,
    g.months_to_zero,
    g.target_value,
    g.commercial_placed_value,
    g.gap_value,
    g.cumplimiento_actual,
    g.economics_conciliacion,
    g.attention_score,
    g.suggested_action,
    g.suggested_owner,

    m.preliminary_delivery_date,
    m.days_to_preliminary_delivery,
    m.schedule_band,

    ctx.highest_claim_level AS evidence_level,
    ctx.context_completeness_pct,

    im.execution_status,
    im.execution_health,
    im.contract_code,
    im.outcome_due_date,
    im.outcome_sla_status

FROM analytics.v_project_growth_state g
LEFT JOIN analytics.v_project_schedule_context_v2921 m
  ON m.project_key=g.project_key
LEFT JOIN analytics.v_project_context_latest_v290 ctx
  ON ctx.project_key=g.project_key
LEFT JOIN decision_intelligence.v_intervention_monitoring_v293 im
  ON im.project_key=g.project_key;


-- Predictive view degrades gracefully to registry-level evidence.
-- It intentionally does not label backtests as prospective.
CREATE OR REPLACE VIEW analytics.v_pbi_predictive_evidence_v293 AS
SELECT
    p.project_key,
    p.project_name,
    p.context_completeness_pct,
    p.highest_claim_level AS evidence_level,
    (p.context_json -> 'predictive_context' ->> 'issues')::integer AS prospective_issue_rows,
    p.context_json -> 'predictive_context' ->> 'next_maturity' AS next_maturity,
    p.context_json -> 'predictive_context' ->> 'performance_rows' AS performance_rows
FROM analytics.v_project_context_latest_v290 p;


CREATE OR REPLACE VIEW analytics.v_ai_control_tower_v293 AS
SELECT * FROM analytics.v_pbi_ai_control_tower_v293;

COMMENT ON VIEW analytics.v_pbi_ai_control_tower_v293 IS
'Stable, flat semantic view for Power BI / Streamlit executive monitoring.';
COMMENT ON VIEW analytics.v_pbi_outcome_roi_v293 IS
'Observed ROI view. ROI is association/accounting evidence unless a causal identification design exists.';
COMMENT ON TABLE decision_intelligence.intervention_ledger_v293 IS
'Execution evidence is separate from contract approval and separate from outcome.';

COMMIT;
