BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE TABLE IF NOT EXISTS analytics.project_milestone_v2921 (
    project_key text PRIMARY KEY,
    project_name text NOT NULL,
    preliminary_delivery_date date NOT NULL,
    delivery_status text NOT NULL DEFAULT 'PRELIMINARY',
    source_type text,
    source_note text,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW analytics.v_project_schedule_context_v2921 AS
SELECT
    m.*,
    (m.preliminary_delivery_date - current_date) AS days_to_preliminary_delivery,
    CASE
        WHEN m.preliminary_delivery_date < current_date THEN 'PAST_PRELIMINARY_DATE'
        WHEN m.preliminary_delivery_date - current_date <= 30 THEN 'CRITICAL'
        WHEN m.preliminary_delivery_date - current_date <= 90 THEN 'LATE'
        WHEN m.preliminary_delivery_date - current_date <= 180 THEN 'MID'
        ELSE 'EARLY'
    END AS schedule_band,
    (m.preliminary_delivery_date < current_date) AS milestone_status_review_required
FROM analytics.project_milestone_v2921 m;

CREATE TABLE IF NOT EXISTS decision_intelligence.project_deadline_recommendation_v2921 (
    recommendation_id bigserial PRIMARY KEY,
    project_key text NOT NULL,
    calculated_at timestamptz NOT NULL DEFAULT now(),
    calculated_for_date date NOT NULL,
    route_status text,
    schedule_band text NOT NULL,
    days_to_preliminary_delivery integer NOT NULL,
    deadline_type text,
    recommended_deadline date,
    default_outcome_window_days integer,
    new_experiment_allowed_by_schedule boolean,
    milestone_status_review_required boolean,
    recommendation_reason text,
    config_version text NOT NULL DEFAULT '2.9.2.1'
);

CREATE INDEX IF NOT EXISTS ix_project_deadline_recommendation_v2921_project_ts
ON decision_intelligence.project_deadline_recommendation_v2921(project_key, calculated_at DESC);

CREATE OR REPLACE VIEW decision_intelligence.v_project_deadline_recommendation_latest_v2921 AS
SELECT *
FROM (
    SELECT
        r.*,
        row_number() OVER (
            PARTITION BY project_key
            ORDER BY calculated_at DESC, recommendation_id DESC
        ) AS rn
    FROM decision_intelligence.project_deadline_recommendation_v2921 r
) x
WHERE rn=1;

COMMENT ON TABLE analytics.project_milestone_v2921 IS
'Preliminary delivery milestones supplied by the business. A past preliminary date does not prove actual delivery.';

COMMENT ON TABLE decision_intelligence.project_deadline_recommendation_v2921 IS
'Advisory deadlines derived from preliminary delivery timing + route policy. They are not approved contract deadlines until a human accepts them.';

COMMIT;
