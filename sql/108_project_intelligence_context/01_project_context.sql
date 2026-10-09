BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

-- ================================================================
-- Medallio v2.9.0 — Project Intelligence Context Layer
--
-- One governed context snapshot per project.
-- The JSON is a compiled evidence packet, not an AI claim by itself.
-- ================================================================

CREATE TABLE IF NOT EXISTS analytics.project_context_snapshot_v290 (
    context_snapshot_id bigserial PRIMARY KEY,
    context_hash text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),

    project_key text NOT NULL,
    project_name text,

    context_version text NOT NULL DEFAULT '2.9.0',
    data_as_of date,

    context_completeness_pct numeric,
    source_relations_available integer,
    source_relations_used integer,

    commercial_context_ready boolean NOT NULL DEFAULT false,
    product_context_ready boolean NOT NULL DEFAULT false,
    pricing_context_ready boolean NOT NULL DEFAULT false,
    predictive_context_ready boolean NOT NULL DEFAULT false,
    decision_context_ready boolean NOT NULL DEFAULT false,
    outcome_context_ready boolean NOT NULL DEFAULT false,

    highest_claim_level text,
    evidence_warning text,

    context_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(project_key, context_hash)
);

CREATE INDEX IF NOT EXISTS ix_project_context_snapshot_v290_project_ts
ON analytics.project_context_snapshot_v290(project_key, captured_at DESC);

CREATE OR REPLACE VIEW analytics.v_project_context_latest_v290 AS
SELECT *
FROM (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY project_key
            ORDER BY captured_at DESC, context_snapshot_id DESC
        ) AS rn
    FROM analytics.project_context_snapshot_v290 s
) x
WHERE rn = 1;

CREATE OR REPLACE VIEW analytics.v_project_context_coverage_v290 AS
SELECT
    count(*) AS projects_profiled,
    round(avg(context_completeness_pct), 1) AS avg_context_completeness_pct,

    count(*) FILTER (WHERE commercial_context_ready) AS commercial_ready,
    count(*) FILTER (WHERE product_context_ready) AS product_ready,
    count(*) FILTER (WHERE pricing_context_ready) AS pricing_ready,
    count(*) FILTER (WHERE predictive_context_ready) AS predictive_ready,
    count(*) FILTER (WHERE decision_context_ready) AS decision_ready,
    count(*) FILTER (WHERE outcome_context_ready) AS outcome_ready,

    max(captured_at) AS latest_context_refresh
FROM analytics.v_project_context_latest_v290;

COMMENT ON TABLE analytics.project_context_snapshot_v290 IS
'Per-project governed evidence packet compiled from Medallio. JSON is context for AI/human analysis; claims remain constrained by evidence gates.';

COMMIT;
