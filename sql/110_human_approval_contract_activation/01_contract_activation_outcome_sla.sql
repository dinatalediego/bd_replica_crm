BEGIN;

CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ================================================================
-- Medallio v2.9.2
-- Human Approval + Contract Activation + Outcome SLA
-- ================================================================

CREATE TABLE IF NOT EXISTS decision_intelligence.project_contract_route_v292 (
    project_key text PRIMARY KEY,
    route_status text NOT NULL,
    activation_eligible boolean NOT NULL DEFAULT false,
    required_gate text,
    route_reason text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE decision_intelligence.project_contract_route_v292 IS
'Explicit portfolio routing policy. v2.9.2 only permits MD and MT to become activation candidates; activation still requires human approval.';


CREATE TABLE IF NOT EXISTS decision_intelligence.project_contract_approval_v292 (
    approval_id bigserial PRIMARY KEY,
    draft_id bigint NOT NULL,
    project_key text NOT NULL,
    project_name text,

    approved_by text NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),

    owner_confirmed text NOT NULL,
    deadline date NOT NULL,
    primary_metric text NOT NULL,
    success_criterion text NOT NULL,

    outcome_window_days integer NOT NULL,
    outcome_capture_method text NOT NULL,
    roi_measurement_plan text NOT NULL,

    action_cost numeric,
    currency text NOT NULL DEFAULT 'PEN',

    baseline_json jsonb NOT NULL,
    baseline_hash text NOT NULL,

    approval_payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'APPROVED_READY',
    revoked_at timestamptz,
    revoked_by text,
    revoke_reason text,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_project_contract_approval_v292_project
ON decision_intelligence.project_contract_approval_v292(project_key, approved_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_project_contract_approval_v292_active_draft
ON decision_intelligence.project_contract_approval_v292(draft_id)
WHERE status = 'APPROVED_READY';


CREATE TABLE IF NOT EXISTS decision_intelligence.project_active_contract_v292 (
    contract_id bigserial PRIMARY KEY,
    contract_code text NOT NULL UNIQUE,

    draft_id bigint NOT NULL,
    approval_id bigint NOT NULL,
    project_key text NOT NULL,
    project_name text,

    route_status_at_activation text NOT NULL,

    hypothesis text,
    proposed_action text,

    owner text NOT NULL,
    deadline date NOT NULL,

    primary_metric text NOT NULL,
    secondary_metrics jsonb,

    baseline_json jsonb NOT NULL,
    baseline_hash text NOT NULL,

    success_criterion text NOT NULL,
    outcome_window_days integer NOT NULL,
    outcome_due_date date NOT NULL,

    action_cost numeric,
    currency text NOT NULL DEFAULT 'PEN',
    outcome_capture_method text NOT NULL,
    roi_measurement_plan text NOT NULL,

    value_at_risk numeric,
    value_to_capture numeric,
    evidence_level text,

    status text NOT NULL DEFAULT 'ACTIVE',

    activated_at timestamptz NOT NULL DEFAULT now(),
    activated_by text NOT NULL,

    cancelled_at timestamptz,
    cancelled_by text,
    cancel_reason text,

    learning_completed_at timestamptz,
    learning_completed_by text,
    learning_summary text,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_project_active_contract_v292_one_open
ON decision_intelligence.project_active_contract_v292(project_key)
WHERE status IN ('ACTIVE', 'WAITING_OUTCOME', 'OUTCOME_MATURE');


CREATE TABLE IF NOT EXISTS decision_intelligence.project_contract_outcome_v292 (
    outcome_id bigserial PRIMARY KEY,
    contract_id bigint NOT NULL,
    project_key text NOT NULL,

    observed_at timestamptz NOT NULL,
    metric_name text NOT NULL,
    metric_value numeric NOT NULL,

    value_realized numeric,
    currency text NOT NULL DEFAULT 'PEN',

    source_reference text,
    evidence_note text,
    recorded_by text NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_project_contract_outcome_v292_contract
ON decision_intelligence.project_contract_outcome_v292(contract_id, observed_at DESC);


CREATE TABLE IF NOT EXISTS decision_intelligence.project_contract_event_v292 (
    event_id bigserial PRIMARY KEY,
    contract_id bigint,
    draft_id bigint,
    project_key text NOT NULL,
    event_type text NOT NULL,
    actor text,
    event_ts timestamptz NOT NULL DEFAULT now(),
    payload jsonb
);

CREATE INDEX IF NOT EXISTS ix_project_contract_event_v292_project_ts
ON decision_intelligence.project_contract_event_v292(project_key, event_ts DESC);


-- Frozen contract fields cannot be rewritten after activation.
CREATE OR REPLACE FUNCTION decision_intelligence.guard_frozen_contract_v292()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.draft_id IS DISTINCT FROM OLD.draft_id
       OR NEW.approval_id IS DISTINCT FROM OLD.approval_id
       OR NEW.project_key IS DISTINCT FROM OLD.project_key
       OR NEW.owner IS DISTINCT FROM OLD.owner
       OR NEW.deadline IS DISTINCT FROM OLD.deadline
       OR NEW.primary_metric IS DISTINCT FROM OLD.primary_metric
       OR NEW.secondary_metrics IS DISTINCT FROM OLD.secondary_metrics
       OR NEW.baseline_json IS DISTINCT FROM OLD.baseline_json
       OR NEW.baseline_hash IS DISTINCT FROM OLD.baseline_hash
       OR NEW.success_criterion IS DISTINCT FROM OLD.success_criterion
       OR NEW.outcome_window_days IS DISTINCT FROM OLD.outcome_window_days
       OR NEW.outcome_due_date IS DISTINCT FROM OLD.outcome_due_date
       OR NEW.action_cost IS DISTINCT FROM OLD.action_cost
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.outcome_capture_method IS DISTINCT FROM OLD.outcome_capture_method
       OR NEW.roi_measurement_plan IS DISTINCT FROM OLD.roi_measurement_plan
    THEN
        RAISE EXCEPTION
            'Frozen contract fields cannot be modified after activation. Cancel and create a new approved contract instead.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_frozen_contract_v292
ON decision_intelligence.project_active_contract_v292;

CREATE TRIGGER trg_guard_frozen_contract_v292
BEFORE UPDATE ON decision_intelligence.project_active_contract_v292
FOR EACH ROW
EXECUTE FUNCTION decision_intelligence.guard_frozen_contract_v292();


CREATE OR REPLACE VIEW decision_intelligence.v_latest_contract_approval_v292 AS
SELECT *
FROM (
    SELECT
        a.*,
        row_number() OVER (
            PARTITION BY project_key
            ORDER BY approved_at DESC, approval_id DESC
        ) AS rn
    FROM decision_intelligence.project_contract_approval_v292 a
    WHERE status = 'APPROVED_READY'
) x
WHERE rn = 1;


CREATE OR REPLACE VIEW decision_intelligence.v_active_contract_latest_outcome_v292 AS
SELECT
    c.*,

    o.outcome_id AS latest_outcome_id,
    o.observed_at AS latest_outcome_at,
    o.metric_name AS latest_outcome_metric,
    o.metric_value AS latest_outcome_value,
    o.value_realized AS latest_value_realized,

    coalesce(oc.outcome_count, 0) AS outcome_count,
    coalesce(oc.mature_outcome_count, 0) AS mature_outcome_count,

    CASE
        WHEN c.status = 'LEARNING_COMPLETE' THEN 'LEARNING_COMPLETE'
        WHEN c.status = 'CANCELLED' THEN 'CANCELLED'

        WHEN coalesce(oc.mature_outcome_count, 0) > 0
            THEN 'OUTCOME_MATURE'

        WHEN current_date > c.outcome_due_date
             AND coalesce(oc.mature_outcome_count, 0) = 0
            THEN 'OUTCOME_SLA_BREACH'

        WHEN current_date > c.deadline
             AND coalesce(oc.outcome_count, 0) = 0
            THEN 'EXECUTION_DEADLINE_BREACH'

        WHEN coalesce(oc.outcome_count, 0) > 0
             AND coalesce(oc.mature_outcome_count, 0) = 0
            THEN 'OUTCOME_IMMATURE'

        WHEN current_date <= c.outcome_due_date
            THEN 'WAITING_OUTCOME'

        ELSE 'ACTIVE'
    END AS sla_status,

    (c.deadline - current_date) AS days_to_deadline,
    (c.outcome_due_date - current_date) AS days_to_outcome_due

FROM decision_intelligence.project_active_contract_v292 c

LEFT JOIN LATERAL (
    SELECT o.*
    FROM decision_intelligence.project_contract_outcome_v292 o
    WHERE o.contract_id = c.contract_id
    ORDER BY o.observed_at DESC, o.outcome_id DESC
    LIMIT 1
) o ON TRUE

LEFT JOIN LATERAL (
    SELECT
        count(*) AS outcome_count,
        count(*) FILTER (
            WHERE observed_at::date >= c.outcome_due_date
        ) AS mature_outcome_count
    FROM decision_intelligence.project_contract_outcome_v292 oo
    WHERE oo.contract_id = c.contract_id
) oc ON TRUE;


CREATE OR REPLACE VIEW decision_intelligence.v_outcome_sla_v292 AS
SELECT
    contract_id,
    contract_code,
    project_key,
    project_name,
    owner,
    deadline,
    primary_metric,
    activated_at,
    outcome_window_days,
    outcome_due_date,
    outcome_count,
    mature_outcome_count,
    latest_outcome_at,
    latest_outcome_value,
    latest_value_realized,
    days_to_deadline,
    days_to_outcome_due,
    sla_status,
    status AS contract_status
FROM decision_intelligence.v_active_contract_latest_outcome_v292
WHERE status <> 'CANCELLED'
ORDER BY
    CASE
        WHEN sla_status = 'OUTCOME_SLA_BREACH' THEN 1
        WHEN sla_status = 'EXECUTION_DEADLINE_BREACH' THEN 2
        WHEN sla_status = 'OUTCOME_MATURE' THEN 3
        WHEN sla_status = 'OUTCOME_IMMATURE' THEN 4
        WHEN sla_status = 'WAITING_OUTCOME' THEN 5
        WHEN sla_status = 'LEARNING_COMPLETE' THEN 6
        ELSE 7
    END,
    outcome_due_date,
    deadline;


CREATE OR REPLACE VIEW decision_intelligence.v_contract_activation_readiness_v292 AS
WITH latest_draft AS (
    SELECT *
    FROM (
        SELECT
            d.*,
            row_number() OVER (
                PARTITION BY project_key
                ORDER BY created_at DESC, draft_id DESC
            ) AS rn
        FROM decision_intelligence.project_decision_contract_draft_v291 d
    ) x
    WHERE rn = 1
),
active_contract AS (
    SELECT *
    FROM (
        SELECT
            c.*,
            row_number() OVER (
                PARTITION BY project_key
                ORDER BY activated_at DESC, contract_id DESC
            ) AS rn
        FROM decision_intelligence.project_active_contract_v292 c
        WHERE status IN ('ACTIVE', 'WAITING_OUTCOME', 'OUTCOME_MATURE', 'LEARNING_COMPLETE')
    ) x
    WHERE rn = 1
)
SELECT
    r.project_key,
    r.route_status,
    r.activation_eligible,
    r.required_gate,
    r.route_reason,

    d.draft_id,
    d.project_name,
    d.archetype,
    d.priority_score,
    d.contract_type,
    d.owner_suggested,
    d.primary_metric,
    d.status AS draft_status,

    a.approval_id,
    a.approved_by,
    a.approved_at,
    a.owner_confirmed,
    a.deadline AS approved_deadline,
    a.success_criterion,
    a.outcome_window_days,

    c.contract_id,
    c.contract_code,
    c.status AS active_contract_status,
    c.activated_at,

    CASE
        WHEN c.contract_id IS NOT NULL THEN c.status
        WHEN NOT r.activation_eligible THEN r.route_status
        WHEN d.draft_id IS NULL THEN 'NO_DRAFT'
        WHEN d.status = 'APPROVED_READY' AND a.approval_id IS NOT NULL THEN 'APPROVED_READY'
        WHEN d.status = 'DRAFT_REVIEW_REQUIRED' THEN 'NEEDS_HUMAN_APPROVAL'
        WHEN d.status = 'REJECTED' THEN 'REJECTED'
        ELSE coalesce(d.status, 'UNKNOWN')
    END AS workflow_status

FROM decision_intelligence.project_contract_route_v292 r
LEFT JOIN latest_draft d
  ON d.project_key = r.project_key
LEFT JOIN decision_intelligence.v_latest_contract_approval_v292 a
  ON a.project_key = r.project_key
LEFT JOIN active_contract c
  ON c.project_key = r.project_key;


CREATE OR REPLACE VIEW analytics.v_contract_command_center_v292 AS
SELECT
    r.project_key,
    r.route_status,
    r.activation_eligible,
    r.required_gate,
    r.route_reason,

    rr.project_name,
    rr.priority_score,
    rr.archetype,
    rr.contract_type,
    rr.workflow_status,
    rr.owner_confirmed,
    rr.approved_deadline,
    rr.contract_code,
    rr.active_contract_status,

    s.primary_metric AS sla_primary_metric,
    s.outcome_due_date,
    s.outcome_count,
    s.mature_outcome_count,
    s.days_to_deadline,
    s.days_to_outcome_due,
    s.sla_status

FROM decision_intelligence.project_contract_route_v292 r
LEFT JOIN decision_intelligence.v_contract_activation_readiness_v292 rr
  ON rr.project_key = r.project_key
LEFT JOIN decision_intelligence.v_outcome_sla_v292 s
  ON s.project_key = r.project_key
ORDER BY
    CASE r.route_status
        WHEN 'ACTIVATION_CANDIDATE' THEN 1
        WHEN 'DESIGN_ONLY' THEN 2
        WHEN 'BLOCKED_RECONCILIATION' THEN 3
        WHEN 'EVIDENCE_BUILDING' THEN 4
        ELSE 9
    END,
    rr.priority_score DESC NULLS LAST,
    r.project_key;


COMMENT ON TABLE decision_intelligence.project_active_contract_v292 IS
'Human-approved active decision contracts. Baseline, metric, success criterion, deadline, action cost and outcome design are frozen on activation.';

COMMENT ON TABLE decision_intelligence.project_contract_outcome_v292 IS
'Observed contract outcomes. A mature outcome is one observed on or after the contract outcome_due_date.';

COMMIT;
