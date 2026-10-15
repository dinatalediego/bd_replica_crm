BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

-- ===============================================================
-- Medallio v2.9.3.2 — Current-State vs Historical Semantics
--
-- Problem fixed:
-- Reissued contracts/interventions leave historical CANCELLED rows.
-- Those rows must remain auditable, but must not contaminate:
--   - current CEO control tower,
--   - current KPI counts,
--   - current contract semantics issues.
-- ===============================================================

CREATE OR REPLACE VIEW decision_intelligence.v_intervention_current_v2932 AS
SELECT *
FROM (
    SELECT
        im.*,
        row_number() OVER (
            PARTITION BY im.project_key
            ORDER BY
                CASE WHEN im.execution_status='CANCELLED' THEN 1 ELSE 0 END,
                im.intervention_id DESC
        ) AS rn
    FROM decision_intelligence.v_intervention_monitoring_v293 im
    WHERE im.execution_status <> 'CANCELLED'
) x
WHERE rn=1;


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

FROM decision_intelligence.v_intervention_current_v2932;


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

FROM decision_intelligence.v_intervention_current_v2932 im
WHERE im.metric_semantics_status <> 'OK';


-- Preserve existing v2.9.3 control-tower columns/order.
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
        WHEN im.metric_semantics_status IN ('COMPOSITE_PRIMARY_METRIC','MISSING_PRIMARY_METRIC')
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

    im.primary_metric_is_atomic,
    im.metric_semantics_status,
    im.outcome_phase_status,
    im.contract_sla_status

FROM analytics.v_contract_command_center_v292 cc
LEFT JOIN analytics.v_project_schedule_context_v2921 m
  ON m.project_key=cc.project_key
LEFT JOIN decision_intelligence.v_intervention_current_v2932 im
  ON im.project_key=cc.project_key
LEFT JOIN analytics.v_project_context_latest_v290 ctx
  ON ctx.project_key=cc.project_key;


COMMENT ON VIEW decision_intelligence.v_intervention_current_v2932 IS
'One current non-cancelled intervention per project. Historical cancelled/reissued interventions remain in v_intervention_monitoring_v293.';

COMMIT;
