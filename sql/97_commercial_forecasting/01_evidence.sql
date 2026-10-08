-- Additive only. No RAW/CORE changes, no source queries to Redshift.
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE TABLE IF NOT EXISTS features.commercial_forecast_snapshots (
    snapshot_id uuid PRIMARY KEY,
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    complete_through date NOT NULL,
    source_semantics text NOT NULL,
    data_sha256 text NOT NULL,
    panel jsonb NOT NULL,
    quality jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS model_control.commercial_forecast_runs (
    run_id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES features.commercial_forecast_snapshots,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    manifest jsonb NOT NULL,
    selected_model text NOT NULL,
    evidence_level text NOT NULL,
    artifact_path text NOT NULL
);
CREATE TABLE IF NOT EXISTS analytics.commercial_forecast_predictions (
    run_id uuid NOT NULL REFERENCES model_control.commercial_forecast_runs,
    project text NOT NULL,
    origin date NOT NULL,
    horizon integer NOT NULL CHECK (horizon BETWEEN 1 AND 6),
    model text NOT NULL,
    prediction numeric NOT NULL CHECK (prediction >= 0),
    stock numeric NOT NULL CHECK (stock >= prediction),
    lower80 numeric, upper80 numeric, lower95 numeric, upper95 numeric,
    is_selected boolean NOT NULL,
    state_probabilities jsonb,
    PRIMARY KEY (run_id,project,horizon,model)
);
CREATE TABLE IF NOT EXISTS analytics.commercial_forecast_backtest (
    run_id uuid NOT NULL REFERENCES model_control.commercial_forecast_runs,
    project text NOT NULL,
    origin date NOT NULL,
    horizon integer NOT NULL,
    model text NOT NULL,
    partition text NOT NULL,
    actual numeric NOT NULL,
    prediction numeric NOT NULL,
    lower80 numeric, upper80 numeric, lower95 numeric, upper95 numeric,
    PRIMARY KEY (run_id,project,origin,horizon,model)
);
CREATE TABLE IF NOT EXISTS decision_intelligence.commercial_forecast_goals (
    origin date NOT NULL,
    project text NOT NULL,
    horizon integer NOT NULL CHECK (horizon BETWEEN 1 AND 6),
    target_sales numeric NOT NULL CHECK (target_sales >= 0),
    owner text NOT NULL,
    PRIMARY KEY (origin,project,horizon)
);
CREATE TABLE IF NOT EXISTS decision_intelligence.commercial_forecast_actions (
    action_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    project text NOT NULL,
    horizon integer NOT NULL,
    model text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    owner text NOT NULL,
    action text NOT NULL,
    cost numeric NOT NULL CHECK (cost >= 0),
    FOREIGN KEY (run_id,project,horizon,model)
        REFERENCES analytics.commercial_forecast_predictions (run_id,project,horizon,model)
);
CREATE TABLE IF NOT EXISTS analytics.commercial_forecast_outcomes (
    run_id uuid NOT NULL,
    project text NOT NULL,
    horizon integer NOT NULL,
    model text NOT NULL,
    measured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    outcome_snapshot_id uuid NOT NULL REFERENCES features.commercial_forecast_snapshots,
    actual numeric NOT NULL,
    eligible_scope boolean NOT NULL,
    eligibility_reason text NOT NULL DEFAULT 'LEGACY_UNASSESSED',
    PRIMARY KEY (run_id,project,horizon,model),
    FOREIGN KEY (run_id,project,horizon,model)
        REFERENCES analytics.commercial_forecast_predictions (run_id,project,horizon,model)
);
ALTER TABLE analytics.commercial_forecast_outcomes
    ADD COLUMN IF NOT EXISTS eligibility_reason text NOT NULL DEFAULT 'LEGACY_UNASSESSED';
CREATE UNIQUE INDEX IF NOT EXISTS commercial_forecast_one_selected
    ON analytics.commercial_forecast_predictions(run_id,project,horizon) WHERE is_selected;
CREATE INDEX IF NOT EXISTS commercial_snapshot_maturity
    ON features.commercial_forecast_snapshots(complete_through,captured_at);
-- Views distinguish historical diagnostic from stored predictions issued before outcomes.
CREATE OR REPLACE VIEW analytics.v_commercial_forecast_current AS
WITH latest AS (
  SELECT run_id FROM model_control.commercial_forecast_runs ORDER BY created_at DESC,run_id DESC LIMIT 1
)
SELECT p.*,p.stock-p.prediction AS stock_remaining,
       r.created_at,r.evidence_level,r.selected_model,
       g.target_sales,g.owner,
       greatest(g.target_sales-p.prediction,0) AS expected_shortfall,
       CASE WHEN g.target_sales IS NULL THEN 'SIN_META'
            WHEN p.prediction < g.target_sales THEN 'REVISAR_BRECHA_COMERCIAL'
            ELSE 'SEGUIMIENTO' END AS recommendation
FROM analytics.commercial_forecast_predictions p
JOIN latest USING (run_id)
JOIN model_control.commercial_forecast_runs r USING (run_id)
LEFT JOIN decision_intelligence.commercial_forecast_goals g USING (origin,project,horizon);
CREATE OR REPLACE VIEW analytics.v_commercial_forecast_performance AS
SELECT p.*,o.actual,o.eligible_scope,o.outcome_snapshot_id,o.measured_at,
       p.prediction-o.actual AS error,
       abs(p.prediction-o.actual) AS absolute_error,
       (o.actual BETWEEN p.lower80 AND p.upper80) AS covered80,
       (o.actual BETWEEN p.lower95 AND p.upper95) AS covered95,
       r.created_at,r.evidence_level,
       (r.created_at AT TIME ZONE 'America/Lima') < (p.origin + (p.horizon+1)*interval '1 month') AS issued_before_outcome_end,
       (r.created_at AT TIME ZONE 'America/Lima') <= (p.origin + interval '1 month') AS issued_before_window_start,
       o.eligibility_reason,
       coalesce(o.eligible_scope AND o.eligibility_reason='COMPATIBLE_SCOPE'
         AND (r.created_at AT TIME ZONE 'America/Lima') < (p.origin + (p.horizon+1)*interval '1 month'),false)
         AS eligible_for_operational_scoring,
       coalesce(o.eligible_scope AND o.eligibility_reason='COMPATIBLE_SCOPE'
         AND (r.created_at AT TIME ZONE 'America/Lima') <= (p.origin + interval '1 month'),false)
         AS eligible_for_strict_prospective_scoring,
       extract(epoch FROM ((r.created_at AT TIME ZONE 'America/Lima')-(p.origin+interval '1 month')))/86400
         AS issuance_delay_days
FROM analytics.commercial_forecast_predictions p
JOIN model_control.commercial_forecast_runs r USING (run_id)
LEFT JOIN analytics.commercial_forecast_outcomes o USING (run_id,project,horizon,model);

CREATE OR REPLACE VIEW analytics.v_commercial_forecast_coverage AS
WITH latest AS (
  SELECT run_id,manifest FROM model_control.commercial_forecast_runs ORDER BY created_at DESC,run_id DESC LIMIT 1
)
SELECT latest.run_id,c.* FROM latest CROSS JOIN LATERAL
jsonb_to_recordset(coalesce(latest.manifest->'coverage_projects','[]'::jsonb))
AS c(project text,status text,stock numeric,history_months integer,review_months integer,
     has_forecast boolean,selected_model text,horizon integer,forecast_cumulative numeric);

CREATE OR REPLACE VIEW analytics.v_commercial_forecast_monitoring AS
SELECT run_id,horizon,count(*) AS projects_predicted,
       count(actual) AS outcomes_captured,
       count(*) FILTER (WHERE eligible_for_strict_prospective_scoring) AS strictly_prospective_outcomes,
       avg(absolute_error) FILTER (WHERE eligible_for_strict_prospective_scoring) AS strictly_prospective_mae,
       count(*) FILTER (WHERE eligible_for_operational_scoring) AS issued_before_close_outcomes,
       avg(absolute_error) FILTER (WHERE eligible_for_operational_scoring) AS as_issued_mae,
       avg(error) FILTER (WHERE eligible_for_operational_scoring) AS as_issued_bias,
       (sum(absolute_error) FILTER (WHERE eligible_for_operational_scoring)) /
       nullif(sum(actual) FILTER (WHERE eligible_for_operational_scoring),0) AS as_issued_wape
FROM analytics.v_commercial_forecast_performance WHERE is_selected GROUP BY run_id,horizon;

-- Application records are append-only, including first mature outcomes.
CREATE OR REPLACE FUNCTION model_control.reject_commercial_evidence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Commercial forecasting evidence is append-only; insert a new version';
END;
$$;
DO $$
DECLARE object_name text;
BEGIN
  FOREACH object_name IN ARRAY ARRAY[
    'features.commercial_forecast_snapshots',
    'model_control.commercial_forecast_runs',
    'analytics.commercial_forecast_predictions',
    'analytics.commercial_forecast_backtest',
    'analytics.commercial_forecast_outcomes',
    'decision_intelligence.commercial_forecast_actions'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=object_name::regclass
                   AND tgname='commercial_evidence_append_only') THEN
      EXECUTE format('CREATE TRIGGER commercial_evidence_append_only BEFORE UPDATE OR DELETE ON %s
                      FOR EACH ROW EXECUTE FUNCTION model_control.reject_commercial_evidence_mutation()',object_name);
    END IF;
  END LOOP;
END;
$$;
