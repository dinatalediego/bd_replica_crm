-- Capa de Decision Intelligence. Ejecutar en PostgreSQL local.
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS experiments;

CREATE TABLE IF NOT EXISTS decision_intelligence.decision_contracts (
    decision_system      text PRIMARY KEY,
    objective            text NOT NULL,
    decision_unit        text NOT NULL,
    decision_owner       text NOT NULL,
    target               text NOT NULL,
    prediction_horizon_days integer NOT NULL CHECK (prediction_horizon_days > 0),
    causal_estimand      text NOT NULL,
    primary_value_metric text NOT NULL,
    feedback_outcome     text NOT NULL,
    contract_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active            boolean NOT NULL DEFAULT true,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_control.model_runs (
    model_run_id         uuid PRIMARY KEY,
    decision_system      text NOT NULL,
    model_name           text NOT NULL,
    model_version        text NOT NULL,
    trained_at           timestamptz NOT NULL DEFAULT now(),
    training_window_from timestamptz,
    training_window_to   timestamptz,
    target               text,
    feature_list         jsonb NOT NULL DEFAULT '[]'::jsonb,
    metrics              jsonb NOT NULL DEFAULT '{}'::jsonb,
    parameters           jsonb NOT NULL DEFAULT '{}'::jsonb,
    artifact_uri         text,
    status               text NOT NULL DEFAULT 'TRAINED'
);

CREATE INDEX IF NOT EXISTS ix_model_runs_system_time
    ON model_control.model_runs (decision_system, trained_at DESC);

CREATE TABLE IF NOT EXISTS decision_intelligence.recommendations (
    recommendation_id    uuid PRIMARY KEY,
    decision_system      text NOT NULL,
    entity_id            text NOT NULL,
    scored_at            timestamptz NOT NULL DEFAULT now(),
    model_run_id         uuid REFERENCES model_control.model_runs(model_run_id),
    predicted_probability double precision,
    expected_value_no_action numeric(18,4),
    expected_incremental_value numeric(18,4),
    expected_value_with_action numeric(18,4),
    recommended_action   text NOT NULL,
    priority_rank        integer,
    context_json         jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_recommendations_system_time
    ON decision_intelligence.recommendations (decision_system, scored_at DESC);
CREATE INDEX IF NOT EXISTS ix_recommendations_entity
    ON decision_intelligence.recommendations (decision_system, entity_id, scored_at DESC);

CREATE TABLE IF NOT EXISTS decision_intelligence.actions (
    action_id             uuid PRIMARY KEY,
    recommendation_id     uuid REFERENCES decision_intelligence.recommendations(recommendation_id),
    decision_system       text NOT NULL,
    entity_id             text NOT NULL,
    action_taken          text NOT NULL,
    action_owner          text,
    action_at             timestamptz NOT NULL DEFAULT now(),
    action_cost           numeric(18,4) NOT NULL DEFAULT 0,
    notes                 text,
    context_json          jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS decision_intelligence.outcomes (
    outcome_id             uuid PRIMARY KEY,
    decision_system       text NOT NULL,
    entity_id             text NOT NULL,
    outcome_name          text NOT NULL,
    outcome_value         numeric(18,4),
    outcome_at            timestamptz NOT NULL,
    realized_value        numeric(18,4),
    source_event_id       text,
    context_json          jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_outcomes_entity
    ON decision_intelligence.outcomes (decision_system, entity_id, outcome_at DESC);

CREATE TABLE IF NOT EXISTS experiments.experiments (
    experiment_id         uuid PRIMARY KEY,
    decision_system       text NOT NULL,
    experiment_name       text NOT NULL,
    hypothesis            text NOT NULL,
    treatment_description text NOT NULL,
    primary_outcome       text NOT NULL,
    causal_estimand       text NOT NULL,
    started_at            timestamptz,
    ended_at              timestamptz,
    status                text NOT NULL DEFAULT 'PLANNED',
    design_json           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS experiments.assignments (
    experiment_id         uuid NOT NULL REFERENCES experiments.experiments(experiment_id),
    entity_id             text NOT NULL,
    treatment_group       text NOT NULL,
    assigned_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (experiment_id, entity_id)
);

CREATE OR REPLACE VIEW decision_intelligence.v_feedback_loop AS
SELECT
    r.recommendation_id,
    r.decision_system,
    r.entity_id,
    r.scored_at,
    r.predicted_probability,
    r.expected_incremental_value,
    r.recommended_action,
    a.action_taken,
    a.action_at,
    a.action_cost,
    o.outcome_name,
    o.outcome_value,
    o.outcome_at,
    o.realized_value
FROM decision_intelligence.recommendations r
LEFT JOIN LATERAL (
    SELECT a1.*
    FROM decision_intelligence.actions a1
    WHERE a1.decision_system = r.decision_system
      AND a1.entity_id = r.entity_id
      AND a1.action_at >= r.scored_at
    ORDER BY a1.action_at
    LIMIT 1
) a ON true
LEFT JOIN LATERAL (
    SELECT o1.*
    FROM decision_intelligence.outcomes o1
    WHERE o1.decision_system = r.decision_system
      AND o1.entity_id = r.entity_id
      AND o1.outcome_at >= r.scored_at
    ORDER BY o1.outcome_at
    LIMIT 1
) o ON true;
