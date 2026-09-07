-- Additive pilot v1. Run explicitly after lead_scoring init, never inside live scoring.
CREATE SCHEMA IF NOT EXISTS experiments;
CREATE TABLE IF NOT EXISTS experiments.lead_pilots (
 pilot_id text PRIMARY KEY,
 protocol jsonb NOT NULL,
 status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','PAUSED','CLOSED')),
 created_at timestamptz NOT NULL DEFAULT now(), activated_at timestamptz,
 approved_by text, updated_at timestamptz NOT NULL DEFAULT now()
);
-- Only one recruiting pilot: avoid competing treatments in the same CRM.
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_lead_pilot
 ON experiments.lead_pilots ((status)) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_audit (
 audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 pilot_id text NOT NULL REFERENCES experiments.lead_pilots,
 event_at timestamptz NOT NULL DEFAULT now(), operator text NOT NULL,
 event_type text NOT NULL, details jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_batches (
 batch_id uuid PRIMARY KEY, pilot_id text NOT NULL REFERENCES experiments.lead_pilots,
 batch_type text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
 source_rows integer NOT NULL, accepted_rows integer NOT NULL,
 existing_rows integer NOT NULL, rejected_rows integer NOT NULL,
 CHECK (source_rows=accepted_rows+existing_rows+rejected_rows)
);
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_rejects (
 batch_id uuid NOT NULL REFERENCES experiments.lead_pilot_batches,
 row_number integer NOT NULL, source_key text, reason text NOT NULL,
 PRIMARY KEY (batch_id,row_number)
);
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_assignments (
 assignment_id uuid PRIMARY KEY,
 pilot_id text NOT NULL REFERENCES experiments.lead_pilots,
 subject_key text NOT NULL, evidence_key text NOT NULL REFERENCES features.lead_evidence,
 score_id uuid NOT NULL REFERENCES decision_intelligence.lead_scores,
 model_run_id uuid NOT NULL REFERENCES model_control.model_runs,
 arm text NOT NULL CHECK (arm IN ('TREATMENT','CONTROL')),
 assigned_at timestamptz NOT NULL DEFAULT now(),
 decision_at timestamptz NOT NULL, scored_at timestamptz NOT NULL,
 codigo_proyecto text NOT NULL, asesor text, canal text,
 priority_score double precision NOT NULL,
 p_separacion_14d double precision NOT NULL, p_minuta_60d double precision NOT NULL,
 UNIQUE (pilot_id,subject_key), UNIQUE (pilot_id,evidence_key)
);
CREATE INDEX IF NOT EXISTS ix_pilot_subject ON experiments.lead_pilot_assignments(subject_key);
CREATE INDEX IF NOT EXISTS ix_pilot_score ON experiments.lead_pilot_assignments(score_id);
CREATE INDEX IF NOT EXISTS ix_pilot_model ON experiments.lead_pilot_assignments(model_run_id);
CREATE INDEX IF NOT EXISTS ix_pilot_evidence ON experiments.lead_pilot_assignments(evidence_key);
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_actions (
 event_id uuid PRIMARY KEY,
 assignment_id uuid NOT NULL REFERENCES experiments.lead_pilot_assignments,
 action_at timestamptz NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 action_type text NOT NULL CHECK (action_type IN ('CALL','WHATSAPP','VISIT_SCHEDULED','VISIT_COMPLETED','NO_CONTACT')),
 result text NOT NULL CHECK (length(trim(result))>0),
 owner text NOT NULL CHECK (length(trim(owner))>0),
 cost_pen numeric(18,4) NOT NULL CHECK (cost_pen>=0),
 source_ref text NOT NULL CHECK (length(trim(source_ref))>0)
);
CREATE INDEX IF NOT EXISTS ix_pilot_action_time ON experiments.lead_pilot_actions(assignment_id,action_at);
-- Final, reviewed observation of the entire horizon, not a current CRM status.
CREATE TABLE IF NOT EXISTS experiments.lead_pilot_outcomes (
 assignment_id uuid NOT NULL REFERENCES experiments.lead_pilot_assignments,
 outcome_name text NOT NULL CHECK (outcome_name IN ('separacion_14d','minuta_60d')),
 value smallint NOT NULL CHECK (value IN (0,1)),
 event_at timestamptz, observed_through timestamptz NOT NULL,
 source_ref text NOT NULL CHECK (length(trim(source_ref))>0),
 verified_by text NOT NULL CHECK (length(trim(verified_by))>0),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (assignment_id,outcome_name),
 CHECK ((value=1 AND event_at IS NOT NULL) OR (value=0 AND event_at IS NULL))
);
CREATE OR REPLACE VIEW experiments.v_lead_pilot_operations AS
SELECT a.*, e.lead_id,
 p.status AS pilot_status,
 CASE WHEN a.arm='TREATMENT' THEN p.protocol->>'treatment_description'
      ELSE p.protocol->>'control_description' END AS assigned_protocol,
 a.assigned_at + (p.protocol->>'sla_minutes')::integer * interval '1 minute' AS contact_due_at,
 x.actions_recorded,x.first_contact_at,x.cost_pen,
 CASE WHEN x.first_contact_at IS NULL THEN NULL
 ELSE extract(epoch FROM (x.first_contact_at-a.assigned_at))/60 END AS minutes_to_attempt,
 a.assigned_at+interval '14 days' AS sep_matures_at,
 a.assigned_at+interval '60 days' AS minuta_matures_at
FROM experiments.lead_pilot_assignments a
JOIN experiments.lead_pilots p USING(pilot_id)
JOIN features.lead_evidence e USING(evidence_key)
LEFT JOIN LATERAL (
 SELECT count(*) AS actions_recorded,
 min(action_at) FILTER (WHERE action_type IN ('CALL','WHATSAPP')) AS first_contact_at,
 coalesce(sum(cost_pen),0) AS cost_pen
 FROM experiments.lead_pilot_actions x WHERE x.assignment_id=a.assignment_id
) x ON true;
-- One row per assignment and endpoint. No joining raw actions to raw outcomes.
CREATE OR REPLACE VIEW experiments.v_lead_pilot_monitor AS
SELECT a.pilot_id,a.assignment_id,a.arm,a.codigo_proyecto,a.asesor,a.canal,
 (a.assigned_at AT TIME ZONE 'America/Lima')::date AS cohort_date,
 a.assigned_at,a.priority_score,a.actions_recorded,a.cost_pen,
 a.first_contact_at IS NOT NULL AND a.first_contact_at<=a.contact_due_at AS sla_met,
 a.first_contact_at IS NULL AND now()>a.contact_due_at AS overdue,
 k.outcome_name,a.assigned_at+k.horizon AS matures_at,
 now()>=a.assigned_at+k.horizon AS mature,
 CASE WHEN now()>=a.assigned_at+k.horizon THEN o.value END AS outcome_value,
 now()>=a.assigned_at+k.horizon AND o.value IS NULL AS missing_mature_outcome
FROM experiments.v_lead_pilot_operations a
CROSS JOIN (VALUES ('separacion_14d',interval '14 days'),('minuta_60d',interval '60 days')) k(outcome_name,horizon)
LEFT JOIN experiments.lead_pilot_outcomes o ON o.assignment_id=a.assignment_id AND o.outcome_name=k.outcome_name;
CREATE OR REPLACE VIEW experiments.v_lead_pilot_summary AS
SELECT pilot_id,arm,cohort_date,codigo_proyecto,outcome_name,
 count(*) AS assigned,
 count(*) FILTER (WHERE mature) AS mature,
 count(outcome_value) AS observed,
 count(*) FILTER (WHERE missing_mature_outcome) AS missing_mature,
 sum(outcome_value) AS positives,
 count(*) FILTER (WHERE actions_recorded>0) AS with_actions,
 count(*) FILTER (WHERE sla_met) AS within_sla,
 sum(cost_pen) AS cost_pen
FROM experiments.v_lead_pilot_monitor
GROUP BY pilot_id,arm,cohort_date,codigo_proyecto,outcome_name;
CREATE OR REPLACE VIEW experiments.v_lead_pilot_reconciliation AS
SELECT b.*,r.reject_details,
 b.source_rows=b.accepted_rows+b.existing_rows+b.rejected_rows AS reconciled
FROM experiments.lead_pilot_batches b
LEFT JOIN LATERAL (
 SELECT jsonb_agg(jsonb_build_object('row',row_number,'key',source_key,'reason',reason)) AS reject_details
 FROM experiments.lead_pilot_rejects r WHERE r.batch_id=b.batch_id
) r ON true;
