BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

-- ===============================================================
-- Medallio v2.9.3.1.1 — VIEW COMPATIBILITY HOTFIX
--
-- PostgreSQL CREATE OR REPLACE VIEW requires existing columns
-- to keep the same names/order. New columns may only be appended.
--
-- This patch:
-- 1) preserves the original v2.9.3 view contract,
-- 2) corrects outcome semantics,
-- 3) appends the new semantic fields at the end,
-- 4) avoids DROP VIEW so downstream dependencies remain intact.
-- ===============================================================

CREATE OR REPLACE VIEW decision_intelligence.v_contract_metric_semantics_v2931 AS
SELECT
    c.contract_id,
    c.contract_code,
    c.project_key,
    c.project_name,
    c.primary_metric,

    CASE
        WHEN c.primary_metric IS NULL OR btrim(c.primary_metric) = ''
            THEN false
        WHEN c.primary_metric ~* '\s+y\s+'
            THEN false
        WHEN c.primary_metric ~* '\s+and\s+'
            THEN false
        WHEN c.primary_metric LIKE '%,%'
            THEN false
        WHEN c.primary_metric LIKE '%;%'
            THEN false
        WHEN c.primary_metric LIKE '%+%'
            THEN false
        WHEN c.primary_metric LIKE '%/%'
            THEN false
        ELSE true
    END AS primary_metric_is_atomic,

    CASE
        WHEN c.primary_metric IS NULL OR btrim(c.primary_metric) = ''
            THEN 'MISSING_PRIMARY_METRIC'
        WHEN c.primary_metric ~* '\s+y\s+'
          OR c.primary_metric ~* '\s+and\s+'
          OR c.primary_metric LIKE '%,%'
          OR c.primary_metric LIKE '%;%'
          OR c.primary_metric LIKE '%+%'
          OR c.primary_metric LIKE '%/%'
            THEN 'COMPOSITE_PRIMARY_METRIC'
        ELSE 'OK'
    END AS metric_semantics_status

FROM decision_intelligence.project_active_contract_v292 c;


-- ----------------------------------------------------------------
-- Preserve ALL original v2.9.3 columns in the same order.
-- Append new columns only after latest_value_realized.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW decision_intelligence.v_intervention_monitoring_v293 AS
SELECT
    -- ---- original v2.9.3 column contract starts here ----
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
        WHEN NOT ms.primary_metric_is_atomic THEN 'BLOCKED_METRIC_SEMANTICS'
        WHEN i.execution_status='COMPLETED' THEN 'EXECUTION_COMPLETE'
        WHEN current_date > c.deadline
             AND i.execution_status IN ('SCHEDULED','STARTED')
            THEN 'EXECUTION_AT_RISK'
        WHEN i.execution_status='SCHEDULED' THEN 'READY_TO_START'
        WHEN i.execution_status='STARTED' THEN 'IN_EXECUTION'
        WHEN i.execution_status='IMPLEMENTED' THEN 'IMPLEMENTED_NOT_CLOSED'
        ELSE i.execution_status
    END AS execution_health,

    -- Keep the existing column NAME and POSITION.
    -- Its semantics are now the corrected business outcome phase.
    CASE
        WHEN i.execution_status='CANCELLED' THEN 'CANCELLED'
        WHEN i.execution_status IN ('SCHEDULED','STARTED','IMPLEMENTED')
            THEN 'NOT_STARTED'
        WHEN i.execution_status='COMPLETED'
             AND coalesce(s.mature_outcome_count,0) > 0
            THEN 'OUTCOME_MATURE'
        WHEN i.execution_status='COMPLETED'
             AND current_date > c.outcome_due_date
             AND coalesce(s.mature_outcome_count,0)=0
            THEN 'OUTCOME_SLA_BREACH'
        WHEN i.execution_status='COMPLETED'
             AND coalesce(s.outcome_count,0) > 0
             AND coalesce(s.mature_outcome_count,0)=0
            THEN 'OUTCOME_IMMATURE'
        WHEN i.execution_status='COMPLETED'
            THEN 'WAITING_OUTCOME'
        ELSE 'NOT_STARTED'
    END AS outcome_sla_status,

    s.outcome_count,
    s.mature_outcome_count,
    s.latest_outcome_at,
    s.latest_outcome_value,
    s.latest_value_realized,
    -- ---- original v2.9.3 column contract ends here ----

    -- New v2.9.3.1 semantic columns APPENDED ONLY
    ms.primary_metric_is_atomic,
    ms.metric_semantics_status,

    CASE
        WHEN i.execution_status='CANCELLED' THEN 'CANCELLED'
        WHEN i.execution_status IN ('SCHEDULED','STARTED','IMPLEMENTED')
            THEN 'NOT_STARTED'
        WHEN i.execution_status='COMPLETED'
             AND coalesce(s.mature_outcome_count,0) > 0
            THEN 'OUTCOME_MATURE'
        WHEN i.execution_status='COMPLETED'
             AND current_date > c.outcome_due_date
             AND coalesce(s.mature_outcome_count,0)=0
            THEN 'OUTCOME_SLA_BREACH'
        WHEN i.execution_status='COMPLETED'
             AND coalesce(s.outcome_count,0) > 0
             AND coalesce(s.mature_outcome_count,0)=0
            THEN 'OUTCOME_IMMATURE'
        WHEN i.execution_status='COMPLETED'
            THEN 'WAITING_OUTCOME'
        ELSE 'NOT_STARTED'
    END AS outcome_phase_status,

    -- Raw v2.9.2 SLA is retained separately.
    s.sla_status AS contract_sla_status

FROM decision_intelligence.intervention_ledger_v293 i
JOIN decision_intelligence.project_active_contract_v292 c
  ON c.contract_id=i.contract_id
LEFT JOIN decision_intelligence.v_contract_metric_semantics_v2931 ms
  ON ms.contract_id=i.contract_id
LEFT JOIN decision_intelligence.v_outcome_sla_v292 s
  ON s.contract_id=i.contract_id;


-- ----------------------------------------------------------------
-- Preserve original Power BI view column names/order.
-- Append semantic additions after what_needs_me_now.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_ai_control_tower_v293 AS
SELECT
    -- original columns
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
        WHEN im.metric_semantics_status='COMPOSITE_PRIMARY_METRIC'
            THEN 'FIX CONTRACT METRIC'
        WHEN im.metric_semantics_status='MISSING_PRIMARY_METRIC'
            THEN 'FIX CONTRACT METRIC'
        WHEN cc.route_status='BLOCKED_RECONCILIATION' THEN 'FIX DATA'
        WHEN cc.route_status='DESIGN_ONLY' THEN 'DESIGN'
        WHEN cc.route_status='EVIDENCE_BUILDING' THEN 'BUILD EVIDENCE'
        WHEN im.execution_health='EXECUTION_AT_RISK' THEN 'ESCALATE EXECUTION'
        WHEN im.execution_status='SCHEDULED' THEN 'START ACTION'
        WHEN im.execution_status IN ('STARTED','IMPLEMENTED') THEN 'MONITOR EXECUTION'
        WHEN im.execution_status='COMPLETED'
             AND im.outcome_phase_status IN ('WAITING_OUTCOME','OUTCOME_IMMATURE')
            THEN 'WAIT OUTCOME'
        WHEN im.execution_status='COMPLETED'
             AND im.outcome_phase_status='OUTCOME_MATURE'
            THEN 'REVIEW OUTCOME'
        WHEN cc.route_status='ACTIVATION_CANDIDATE' THEN 'REVIEW CONTRACT'
        ELSE 'MONITOR'
    END AS what_needs_me_now,

    -- appended v2.9.3.1 columns
    im.primary_metric_is_atomic,
    im.metric_semantics_status,
    im.outcome_phase_status,
    im.contract_sla_status

FROM analytics.v_contract_command_center_v292 cc
LEFT JOIN analytics.v_project_schedule_context_v2921 m
  ON m.project_key=cc.project_key
LEFT JOIN decision_intelligence.v_intervention_monitoring_v293 im
  ON im.project_key=cc.project_key
LEFT JOIN analytics.v_project_context_latest_v290 ctx
  ON ctx.project_key=cc.project_key;


-- ----------------------------------------------------------------
-- Preserve original ROI view columns/order; append semantics.
-- ----------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_outcome_roi_v293 AS
SELECT
    -- original columns
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

    'OBSERVED_ASSOCIATION_NOT_CAUSAL_PROOF'::text AS roi_interpretation,

    -- appended columns
    im.primary_metric_is_atomic,
    im.metric_semantics_status,
    im.outcome_phase_status,
    im.contract_sla_status

FROM decision_intelligence.v_intervention_monitoring_v293 im;


CREATE OR REPLACE VIEW analytics.v_ai_control_tower_kpis_v2931 AS
SELECT
    count(*) FILTER (
        WHERE execution_status='SCHEDULED'
    ) AS scheduled_interventions,

    count(*) FILTER (
        WHERE execution_status IN ('STARTED','IMPLEMENTED')
    ) AS active_executions,

    count(*) FILTER (
        WHERE outcome_phase_status IN ('WAITING_OUTCOME','OUTCOME_IMMATURE')
    ) AS waiting_outcomes,

    coalesce(sum(mature_outcome_count),0) AS mature_outcomes,

    count(*) FILTER (
        WHERE execution_health='EXECUTION_AT_RISK'
    ) AS executions_at_risk,

    count(*) FILTER (
        WHERE metric_semantics_status <> 'OK'
    ) AS contracts_with_metric_semantics_issue

FROM decision_intelligence.v_intervention_monitoring_v293;


CREATE OR REPLACE VIEW analytics.v_pbi_contract_semantics_issues_v2931 AS
SELECT
    im.project_key,
    im.project_name,
    im.contract_code,
    im.primary_metric,
    im.primary_metric_is_atomic,
    im.metric_semantics_status,
    im.execution_status,
    im.execution_health,

    CASE
        WHEN im.metric_semantics_status='COMPOSITE_PRIMARY_METRIC'
        THEN 'Cancel/reissue before STARTED. Select one atomic primary metric; keep others as secondary metrics.'
        WHEN im.metric_semantics_status='MISSING_PRIMARY_METRIC'
        THEN 'Cancel/reissue before STARTED with one atomic primary metric.'
        ELSE NULL
    END AS recommended_action

FROM decision_intelligence.v_intervention_monitoring_v293 im
WHERE im.metric_semantics_status <> 'OK';


COMMENT ON VIEW analytics.v_ai_control_tower_kpis_v2931 IS
'Executive stage counts with outcome phase separated from pre-execution.';

COMMENT ON VIEW analytics.v_pbi_contract_semantics_issues_v2931 IS
'Frozen active contracts with invalid primary metric semantics. Do not mutate; cancel/reissue before execution.';

COMMIT;
