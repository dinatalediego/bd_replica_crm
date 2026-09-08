-- Decision Policy V2.1: Frozen Cohort + exact allocation + no re-entry + run identity.
-- PostgreSQL local / medallio_dw.
-- Additive and non-destructive: preserves legacy experiments/recommendations.

BEGIN;

CREATE SCHEMA IF NOT EXISTS experiments;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------------
-- 01. Policy run identity
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experiments.policy_runs (
    policy_run_id uuid PRIMARY KEY,
    experiment_id uuid NOT NULL REFERENCES experiments.experiments(experiment_id),
    decision_system text NOT NULL,
    policy_id text NOT NULL,
    policy_version text NOT NULL,
    run_key text NOT NULL,
    run_type text NOT NULL DEFAULT 'PILOT_COHORT'
        CHECK (run_type IN ('PILOT_COHORT','DAILY_BATCH')),
    status text NOT NULL DEFAULT 'PLANNED'
        CHECK (status IN ('PLANNED','ALLOCATING','FROZEN','ACTIVE','COMPLETED','CANCELLED')),
    cohort_size integer NOT NULL CHECK (cohort_size > 0),
    treatment_target_n integer NOT NULL CHECK (treatment_target_n >= 0),
    control_target_n integer NOT NULL CHECK (control_target_n >= 0),
    treatment_share double precision NOT NULL CHECK (treatment_share >= 0 AND treatment_share <= 1),
    selection_window_days integer NOT NULL CHECK (selection_window_days > 0),
    allocation_method text NOT NULL DEFAULT 'DETERMINISTIC_HASH_EXACT',
    allocation_seed text NOT NULL,
    selection_as_of timestamptz NOT NULL,
    frozen_at timestamptz,
    activated_at timestamptz,
    completed_at timestamptz,
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, run_key),
    CHECK (treatment_target_n + control_target_n = cohort_size)
);

CREATE INDEX IF NOT EXISTS ix_policy_runs_policy_time
    ON experiments.policy_runs (decision_system, policy_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 02. Frozen assignment snapshot
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experiments.policy_run_assignments (
    policy_run_id uuid NOT NULL REFERENCES experiments.policy_runs(policy_run_id),
    experiment_id uuid NOT NULL REFERENCES experiments.experiments(experiment_id),
    entity_id text NOT NULL,
    score_id uuid REFERENCES decision_intelligence.lead_scores(score_id),
    model_run_id uuid REFERENCES model_control.model_runs(model_run_id),
    policy_rank integer NOT NULL CHECK (policy_rank > 0),
    assignment_order integer NOT NULL CHECK (assignment_order > 0),
    treatment_group text NOT NULL CHECK (treatment_group IN ('TREATMENT','CONTROL')),
    priority_band text NOT NULL CHECK (priority_band IN ('A','B','C','D')),
    priority_score double precision NOT NULL,
    p_separacion_14d double precision,
    p_minuta_60d double precision,
    decision_at timestamptz NOT NULL,
    codigo_proyecto text,
    asesor text,
    canal text,
    medio text,
    action_owner_proposed text,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (policy_run_id, entity_id),
    UNIQUE (policy_run_id, assignment_order),
    -- This is the hard no-re-entry contract inside one experiment, across runs.
    UNIQUE (experiment_id, entity_id)
);

CREATE INDEX IF NOT EXISTS ix_policy_run_assignments_group
    ON experiments.policy_run_assignments (policy_run_id, treatment_group, assignment_order);
CREATE INDEX IF NOT EXISTS ix_policy_run_assignments_entity
    ON experiments.policy_run_assignments (entity_id, assigned_at DESC);

-- ---------------------------------------------------------------------------
-- 03. Frozen cohort immutability
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION experiments.guard_frozen_policy_run_assignment()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_status text;
BEGIN
    SELECT status INTO v_status
    FROM experiments.policy_runs
    WHERE policy_run_id = OLD.policy_run_id;

    IF v_status IN ('FROZEN','ACTIVE','COMPLETED') THEN
        RAISE EXCEPTION
            'policy_run_id=% is %, assignments are immutable',
            OLD.policy_run_id, v_status;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_frozen_policy_run_assignment
    ON experiments.policy_run_assignments;
CREATE TRIGGER trg_guard_frozen_policy_run_assignment
BEFORE UPDATE OR DELETE ON experiments.policy_run_assignments
FOR EACH ROW EXECUTE FUNCTION experiments.guard_frozen_policy_run_assignment();

CREATE OR REPLACE FUNCTION experiments.guard_frozen_policy_run_config()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('FROZEN','ACTIVE','COMPLETED') AND (
           NEW.experiment_id IS DISTINCT FROM OLD.experiment_id
        OR NEW.decision_system IS DISTINCT FROM OLD.decision_system
        OR NEW.policy_id IS DISTINCT FROM OLD.policy_id
        OR NEW.policy_version IS DISTINCT FROM OLD.policy_version
        OR NEW.run_key IS DISTINCT FROM OLD.run_key
        OR NEW.run_type IS DISTINCT FROM OLD.run_type
        OR NEW.cohort_size IS DISTINCT FROM OLD.cohort_size
        OR NEW.treatment_target_n IS DISTINCT FROM OLD.treatment_target_n
        OR NEW.control_target_n IS DISTINCT FROM OLD.control_target_n
        OR NEW.treatment_share IS DISTINCT FROM OLD.treatment_share
        OR NEW.selection_window_days IS DISTINCT FROM OLD.selection_window_days
        OR NEW.allocation_method IS DISTINCT FROM OLD.allocation_method
        OR NEW.allocation_seed IS DISTINCT FROM OLD.allocation_seed
        OR NEW.selection_as_of IS DISTINCT FROM OLD.selection_as_of
        OR NEW.config_json IS DISTINCT FROM OLD.config_json
    ) THEN
        RAISE EXCEPTION
            'policy_run_id=% configuration is immutable after freeze',
            OLD.policy_run_id;
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_frozen_policy_run_config
    ON experiments.policy_runs;
CREATE TRIGGER trg_guard_frozen_policy_run_config
BEFORE UPDATE ON experiments.policy_runs
FOR EACH ROW EXECUTE FUNCTION experiments.guard_frozen_policy_run_config();

-- ---------------------------------------------------------------------------
-- 04. Atomic freeze gate: exact cohort and exact allocation are mandatory.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION experiments.freeze_policy_run(p_policy_run_id uuid)
RETURNS TABLE (
    policy_run_id uuid,
    status text,
    cohort_n bigint,
    treatment_n bigint,
    control_n bigint,
    frozen_at timestamptz
)
LANGUAGE plpgsql
AS $$
DECLARE
    r experiments.policy_runs%ROWTYPE;
    v_total bigint;
    v_treatment bigint;
    v_control bigint;
BEGIN
    SELECT * INTO r
    FROM experiments.policy_runs
    WHERE experiments.policy_runs.policy_run_id = p_policy_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown policy_run_id=%', p_policy_run_id;
    END IF;

    IF r.status IN ('FROZEN','ACTIVE','COMPLETED') THEN
        RETURN QUERY
        SELECT r.policy_run_id, r.status,
               COUNT(*)::bigint,
               COUNT(*) FILTER (WHERE a.treatment_group='TREATMENT')::bigint,
               COUNT(*) FILTER (WHERE a.treatment_group='CONTROL')::bigint,
               r.frozen_at
        FROM experiments.policy_run_assignments a
        WHERE a.policy_run_id = r.policy_run_id;
        RETURN;
    END IF;

    SELECT
        COUNT(*)::bigint,
        COUNT(*) FILTER (WHERE treatment_group='TREATMENT')::bigint,
        COUNT(*) FILTER (WHERE treatment_group='CONTROL')::bigint
    INTO v_total, v_treatment, v_control
    FROM experiments.policy_run_assignments
    WHERE experiments.policy_run_assignments.policy_run_id = p_policy_run_id;

    IF v_total <> r.cohort_size THEN
        RAISE EXCEPTION 'Cannot freeze run %. cohort=% target=%', p_policy_run_id, v_total, r.cohort_size;
    END IF;
    IF v_treatment <> r.treatment_target_n THEN
        RAISE EXCEPTION 'Cannot freeze run %. treatment=% target=%', p_policy_run_id, v_treatment, r.treatment_target_n;
    END IF;
    IF v_control <> r.control_target_n THEN
        RAISE EXCEPTION 'Cannot freeze run %. control=% target=%', p_policy_run_id, v_control, r.control_target_n;
    END IF;

    UPDATE experiments.policy_runs
    SET status='FROZEN', frozen_at=COALESCE(frozen_at,now()), updated_at=now()
    WHERE experiments.policy_runs.policy_run_id = p_policy_run_id
    RETURNING * INTO r;

    RETURN QUERY SELECT r.policy_run_id, r.status, v_total, v_treatment, v_control, r.frozen_at;
END;
$$;

-- ---------------------------------------------------------------------------
-- 05. Run status / contamination / action readiness
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW experiments.v_policy_run_status AS
WITH assignment_counts AS (
    SELECT
        a.policy_run_id,
        COUNT(*)::bigint AS cohort_n,
        COUNT(*) FILTER (WHERE a.treatment_group='TREATMENT')::bigint AS treatment_n,
        COUNT(*) FILTER (WHERE a.treatment_group='CONTROL')::bigint AS control_n
    FROM experiments.policy_run_assignments a
    GROUP BY a.policy_run_id
),
rec_counts AS (
    SELECT
        NULLIF(r.context_json->>'policy_run_id','')::uuid AS policy_run_id,
        COUNT(*)::bigint AS recommendations_n,
        COUNT(*) FILTER (WHERE r.context_json->>'treatment_group'='CONTROL')::bigint AS control_recommendations_n,
        COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM decision_intelligence.actions a
            WHERE a.recommendation_id=r.recommendation_id
        ))::bigint AS actions_n
    FROM decision_intelligence.recommendations r
    WHERE r.decision_system='priorizacion_leads'
      AND NULLIF(r.context_json->>'policy_run_id','') IS NOT NULL
    GROUP BY NULLIF(r.context_json->>'policy_run_id','')::uuid
)
SELECT
    pr.policy_run_id,
    pr.experiment_id,
    pr.decision_system,
    pr.policy_id,
    pr.policy_version,
    pr.run_key,
    pr.run_type,
    pr.status,
    pr.cohort_size,
    pr.treatment_target_n,
    pr.control_target_n,
    COALESCE(ac.cohort_n,0)::bigint AS cohort_n,
    COALESCE(ac.treatment_n,0)::bigint AS treatment_n,
    COALESCE(ac.control_n,0)::bigint AS control_n,
    COALESCE(rc.recommendations_n,0)::bigint AS recommendations_n,
    COALESCE(rc.actions_n,0)::bigint AS actions_n,
    COALESCE(rc.control_recommendations_n,0)::bigint AS control_recommendations_n,
    (COALESCE(ac.cohort_n,0)=pr.cohort_size
     AND COALESCE(ac.treatment_n,0)=pr.treatment_target_n
     AND COALESCE(ac.control_n,0)=pr.control_target_n) AS exact_allocation_ok,
    (COALESCE(rc.control_recommendations_n,0)=0) AS control_clean,
    (pr.status IN ('FROZEN','ACTIVE','COMPLETED')
     AND COALESCE(ac.cohort_n,0)=pr.cohort_size
     AND COALESCE(ac.treatment_n,0)=pr.treatment_target_n
     AND COALESCE(ac.control_n,0)=pr.control_target_n
     AND COALESCE(rc.control_recommendations_n,0)=0) AS action_ready,
    pr.selection_as_of,
    pr.frozen_at,
    pr.activated_at,
    pr.completed_at,
    pr.created_at,
    pr.updated_at
FROM experiments.policy_runs pr
LEFT JOIN assignment_counts ac USING (policy_run_id)
LEFT JOIN rec_counts rc USING (policy_run_id);

-- ---------------------------------------------------------------------------
-- 06. Reconciliation: pre-V2.1 recommendations remain visible but are NOT
--     action-ready under the frozen-cohort contract.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW experiments.v_policy_legacy_recommendations AS
SELECT
    r.recommendation_id::text AS recommendation_id,
    r.entity_id AS evidence_key,
    r.scored_at,
    COALESCE(NULLIF(r.context_json->>'policy_id',''),'legacy_unversioned') AS policy_id,
    NULLIF(r.context_json->>'policy_version','') AS policy_version,
    NULLIF(r.context_json->>'experiment_id','') AS experiment_id,
    NULLIF(r.context_json->>'policy_run_id','') AS policy_run_id,
    r.recommended_action,
    EXISTS (
        SELECT 1 FROM decision_intelligence.actions a
        WHERE a.recommendation_id=r.recommendation_id
    ) AS has_action
FROM decision_intelligence.recommendations r
WHERE r.decision_system='priorizacion_leads'
  AND COALESCE(NULLIF(r.context_json->>'policy_id',''),'legacy_unversioned') IN ('lead_priority_v2','lead_priority_v2_1')
  AND NULLIF(r.context_json->>'policy_run_id','') IS NULL;

-- ---------------------------------------------------------------------------
-- 07. Power BI run-level blocks
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_policy_runs AS
SELECT * FROM experiments.v_policy_run_status;

CREATE OR REPLACE VIEW analytics.v_pbi_policy_run_assignments AS
SELECT
    a.policy_run_id::text AS policy_run_id,
    a.experiment_id::text AS experiment_id,
    pr.policy_id,
    pr.policy_version,
    pr.run_key,
    pr.status AS run_status,
    a.entity_id AS evidence_key,
    e.lead_id,
    a.policy_rank,
    a.assignment_order,
    a.treatment_group,
    a.priority_band,
    a.priority_score,
    a.p_separacion_14d,
    a.p_minuta_60d,
    a.decision_at,
    a.codigo_proyecto,
    a.asesor,
    a.canal,
    a.medio,
    a.action_owner_proposed,
    a.assigned_at,
    pr.selection_as_of,
    pr.frozen_at
FROM experiments.policy_run_assignments a
JOIN experiments.policy_runs pr USING (policy_run_id)
LEFT JOIN features.lead_evidence e ON e.evidence_key=a.entity_id;

COMMENT ON VIEW analytics.v_pbi_policy_runs IS
'Policy V2.1 run registry: frozen cohort, exact allocation, contamination and action-readiness gates.';
COMMENT ON VIEW analytics.v_pbi_policy_run_assignments IS
'Policy V2.1 frozen assignment fact with run identity and treatment/control snapshot.';

COMMIT;
