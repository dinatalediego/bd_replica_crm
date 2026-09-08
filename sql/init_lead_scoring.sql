-- Lead Scoring v0.1: evidencia point-in-time + challenger/champion + scoring diario.
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE TABLE IF NOT EXISTS features.lead_evidence (
 evidence_key text PRIMARY KEY, lead_id text NOT NULL, decision_at timestamptz NOT NULL,
 captured_at timestamptz NOT NULL DEFAULT now(), evidence_source text NOT NULL CHECK (evidence_source IN ('LIVE','BACKFILL_INFERRED')),
 documento_cliente text NOT NULL, codigo_proyecto text NOT NULL, asesor text, canal text, medio text,
 hour_of_day smallint, day_of_week smallint, is_weekend smallint,
 client_prior_assignments_90d integer, days_since_previous_assignment double precision,
 project_leads_90d integer, project_sep_rate_90d double precision, project_minuta_rate_180d double precision,
 advisor_leads_90d integer, advisor_sep_rate_90d double precision, advisor_minuta_rate_180d double precision,
 global_sep_rate_90d double precision, global_minuta_rate_180d double precision,
 separacion_14d smallint CHECK (separacion_14d IN (0,1)), minuta_60d smallint CHECK (minuta_60d IN (0,1)),
 labels_as_of date, label_status text NOT NULL DEFAULT 'PENDING' CHECK (label_status IN ('PENDING','SEP_MATURED','MATURED')),
 features_refreshed_at timestamptz, feature_payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_lead_evidence_decision_at ON features.lead_evidence (decision_at DESC);
CREATE INDEX IF NOT EXISTS ix_lead_evidence_project_time ON features.lead_evidence (codigo_proyecto, decision_at DESC);
CREATE INDEX IF NOT EXISTS ix_lead_evidence_advisor_time ON features.lead_evidence (asesor, decision_at DESC);
CREATE INDEX IF NOT EXISTS ix_lead_evidence_document_time ON features.lead_evidence (documento_cliente, decision_at DESC);

CREATE TABLE IF NOT EXISTS model_control.scoring_batches (
 scoring_batch_id uuid PRIMARY KEY, model_run_id uuid REFERENCES model_control.model_runs(model_run_id),
 decision_system text NOT NULL, model_name text NOT NULL, model_version text, scored_at timestamptz NOT NULL DEFAULT now(),
 data_as_of timestamptz, rows_scored bigint NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'SUCCESS',
 drift_score double precision, drift_status text, metrics jsonb NOT NULL DEFAULT '{}'::jsonb, notes text
);
CREATE TABLE IF NOT EXISTS model_control.model_aliases (
 decision_system text NOT NULL, model_name text NOT NULL, alias_name text NOT NULL CHECK (alias_name IN ('serving','champion')),
 model_run_id uuid NOT NULL REFERENCES model_control.model_runs(model_run_id), updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (decision_system, model_name, alias_name)
);
CREATE TABLE IF NOT EXISTS model_control.model_promotions (
 promotion_id uuid PRIMARY KEY, decision_system text NOT NULL, model_name text NOT NULL,
 candidate_model_run_id uuid NOT NULL REFERENCES model_control.model_runs(model_run_id),
 incumbent_model_run_id uuid REFERENCES model_control.model_runs(model_run_id), evaluated_at timestamptz NOT NULL DEFAULT now(),
 gate_status text NOT NULL CHECK (gate_status IN ('PASS','FAIL')),
 decision text NOT NULL CHECK (decision IN ('PROVISIONAL_SERVING','PASS_FOR_REVIEW','REJECT','PROMOTED')),
 gate_details jsonb NOT NULL DEFAULT '{}'::jsonb, reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
 approved_at timestamptz, approved_by text
);
CREATE TABLE IF NOT EXISTS decision_intelligence.lead_scores (
 score_id uuid PRIMARY KEY, evidence_key text NOT NULL REFERENCES features.lead_evidence(evidence_key),
 lead_id text NOT NULL, decision_at timestamptz NOT NULL, scored_at timestamptz NOT NULL DEFAULT now(),
 model_run_id uuid NOT NULL REFERENCES model_control.model_runs(model_run_id),
 p_separacion_14d double precision NOT NULL CHECK (p_separacion_14d BETWEEN 0 AND 1),
 p_minuta_60d double precision NOT NULL CHECK (p_minuta_60d BETWEEN 0 AND 1),
 priority_score double precision NOT NULL CHECK (priority_score BETWEEN 0 AND 100),
 priority_rank integer NOT NULL CHECK (priority_rank > 0), priority_band text NOT NULL CHECK (priority_band IN ('A','B','C','D')),
 is_provisional boolean NOT NULL DEFAULT true, context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE (evidence_key, model_run_id)
);
CREATE INDEX IF NOT EXISTS ix_lead_scores_time_rank ON decision_intelligence.lead_scores (scored_at DESC, priority_rank);

CREATE OR REPLACE VIEW decision_intelligence.v_lead_priority_current AS
SELECT DISTINCT ON (s.evidence_key)
 s.evidence_key,s.lead_id,e.documento_cliente,e.codigo_proyecto,e.asesor,e.canal,e.medio,
 s.decision_at,s.decision_at::date AS decision_date,s.scored_at,mr.model_version,mr.status AS model_status,
 s.is_provisional,s.p_separacion_14d,s.p_minuta_60d,s.priority_score,s.priority_rank,s.priority_band,
 e.label_status,e.separacion_14d,e.minuta_60d
FROM decision_intelligence.lead_scores s
JOIN features.lead_evidence e USING (evidence_key)
JOIN model_control.model_runs mr ON mr.model_run_id=s.model_run_id
JOIN model_control.model_aliases a ON a.model_run_id=s.model_run_id AND a.decision_system=mr.decision_system
 AND a.model_name=mr.model_name AND a.alias_name='serving'
ORDER BY s.evidence_key,s.scored_at DESC;

CREATE OR REPLACE VIEW decision_intelligence.v_lead_score_matured_performance AS
SELECT mr.model_version,s.priority_band,
 COUNT(*) FILTER (WHERE e.separacion_14d IS NOT NULL)::bigint AS n_sep_matured,
 AVG(e.separacion_14d::double precision) FILTER (WHERE e.separacion_14d IS NOT NULL) AS actual_sep_rate,
 AVG(s.p_separacion_14d) FILTER (WHERE e.separacion_14d IS NOT NULL) AS predicted_sep_rate,
 COUNT(*) FILTER (WHERE e.minuta_60d IS NOT NULL)::bigint AS n_minuta_matured,
 AVG(e.minuta_60d::double precision) FILTER (WHERE e.minuta_60d IS NOT NULL) AS actual_minuta_rate,
 AVG(s.p_minuta_60d) FILTER (WHERE e.minuta_60d IS NOT NULL) AS predicted_minuta_rate,
 AVG(s.priority_score) AS avg_priority_score
FROM decision_intelligence.lead_scores s
JOIN features.lead_evidence e USING (evidence_key)
JOIN model_control.model_runs mr ON mr.model_run_id=s.model_run_id
GROUP BY mr.model_version,s.priority_band;

CREATE OR REPLACE VIEW model_control.v_lead_model_aliases AS
SELECT a.decision_system,a.model_name,a.alias_name,a.model_run_id,mr.model_version,mr.trained_at,mr.status,a.updated_at
FROM model_control.model_aliases a JOIN model_control.model_runs mr USING (model_run_id)
WHERE a.decision_system='priorizacion_leads' AND a.model_name='lead_priority_bundle';

INSERT INTO decision_intelligence.decision_contracts
  (decision_system,objective,decision_unit,decision_owner,target,prediction_horizon_days,
   causal_estimand,primary_value_metric,feedback_outcome,contract_json,is_active,updated_at)
VALUES
  ('priorizacion_leads','Priorizar atención comercial con evidencia point-in-time',
   'asignacion de lead (evidence_key)','supervisor comercial','minuta_60d',60,
   'No identificado en v0: propensión, no uplift','tasa de minuta y valor incremental futuro',
   'separacion_14d + minuta_60d',
   '{"human_in_the_loop":true,"automatic_contact":false,"semantics":"PROPENSITY_NOT_CAUSAL_UPLIFT"}'::jsonb,
   true,now())
ON CONFLICT (decision_system) DO UPDATE SET
  objective=EXCLUDED.objective,decision_unit=EXCLUDED.decision_unit,
  decision_owner=EXCLUDED.decision_owner,target=EXCLUDED.target,
  prediction_horizon_days=EXCLUDED.prediction_horizon_days,
  causal_estimand=EXCLUDED.causal_estimand,primary_value_metric=EXCLUDED.primary_value_metric,
  feedback_outcome=EXCLUDED.feedback_outcome,contract_json=EXCLUDED.contract_json,
  is_active=true,updated_at=now();

CREATE OR REPLACE VIEW decision_intelligence.v_lead_action_outcome AS
SELECT
 r.recommendation_id,r.entity_id AS evidence_key,
 r.context_json->>'lead_id' AS lead_id,
 r.scored_at::date AS decision_date,r.scored_at,r.model_run_id,
 r.context_json->>'priority_band' AS priority_band,
 (r.context_json->>'priority_score')::double precision AS priority_score,
 r.predicted_probability AS p_minuta_60d,r.recommended_action,
 a.action_id,a.action_taken,a.action_owner,a.action_at,a.action_cost,
 CASE WHEN a.action_id IS NULL THEN 'NOT_RECORDED' ELSE 'RECORDED' END AS action_status,
 CASE WHEN a.action_id IS NULL THEN NULL ELSE a.action_taken=r.recommended_action END AS followed_recommendation,
 sep.outcome_value AS separacion_14d,sep.outcome_at AS separacion_observed_at,
 minuta.outcome_value AS minuta_60d,minuta.outcome_at AS minuta_observed_at
FROM decision_intelligence.recommendations r
LEFT JOIN LATERAL (
 SELECT a1.* FROM decision_intelligence.actions a1
 WHERE a1.recommendation_id=r.recommendation_id ORDER BY a1.action_at LIMIT 1
) a ON true
LEFT JOIN decision_intelligence.outcomes sep
 ON sep.decision_system=r.decision_system AND sep.entity_id=r.entity_id AND sep.outcome_name='separacion_14d'
LEFT JOIN decision_intelligence.outcomes minuta
 ON minuta.decision_system=r.decision_system AND minuta.entity_id=r.entity_id AND minuta.outcome_name='minuta_60d'
WHERE r.decision_system='priorizacion_leads';

CREATE OR REPLACE VIEW decision_intelligence.v_lead_action_outcome_performance AS
SELECT
 decision_date,priority_band,action_status,COALESCE(action_taken,'SIN_ACCION_REGISTRADA') AS action_taken,
 COUNT(*)::bigint AS recommendations,
 COUNT(action_id)::bigint AS actions_recorded,
 COUNT(separacion_14d)::bigint AS sep_matured,
 AVG(separacion_14d) AS sep_rate,
 COUNT(minuta_60d)::bigint AS minuta_matured,
 AVG(minuta_60d) AS minuta_rate,
 COALESCE(SUM(action_cost),0) AS total_action_cost
FROM decision_intelligence.v_lead_action_outcome
GROUP BY decision_date,priority_band,action_status,COALESCE(action_taken,'SIN_ACCION_REGISTRADA');
