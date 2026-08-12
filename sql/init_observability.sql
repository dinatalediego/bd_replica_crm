-- Sprint 1: observabilidad de datos para Medallio Control Tower.
-- Ejecutar en PostgreSQL local (medallio_dw).

CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE IF NOT EXISTS observability.asset_registry (
    asset_key                       text PRIMARY KEY,
    source_schema                   text NOT NULL,
    source_table                    text NOT NULL,
    target_schema                   text NOT NULL,
    target_table                    text NOT NULL,
    layer                           text NOT NULL DEFAULT 'raw',
    enabled                         boolean NOT NULL DEFAULT true,
    criticality                     text NOT NULL DEFAULT 'high',
    business_domain                 text NOT NULL DEFAULT 'Commercial Analytics',
    business_process                text,
    business_owner                  text,
    business_impact                 text,
    downstream_products             text,
    expected_frequency_minutes      integer NOT NULL DEFAULT 60 CHECK (expected_frequency_minutes > 0),
    freshness_sla_minutes           integer NOT NULL DEFAULT 90 CHECK (freshness_sla_minutes > 0),
    replication_lag_sla_minutes     integer NOT NULL DEFAULT 90 CHECK (replication_lag_sla_minutes >= 0),
    reconciliation_tolerance_pct    numeric(10,4) NOT NULL DEFAULT 1.0 CHECK (reconciliation_tolerance_pct >= 0),
    strategy                        text NOT NULL,
    watermark_column                text,
    key_columns                     text[] NOT NULL DEFAULT ARRAY[]::text[],
    monitor_source_watermark        boolean NOT NULL DEFAULT true,
    deep_quality_enabled            boolean NOT NULL DEFAULT true,
    updated_at                      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observability.asset_snapshots (
    snapshot_id                 bigserial PRIMARY KEY,
    snapshot_at                 timestamptz NOT NULL DEFAULT now(),
    mode                        text NOT NULL CHECK (mode IN ('hourly','deep')),
    asset_key                   text NOT NULL REFERENCES observability.asset_registry(asset_key),
    last_run_status             text,
    last_run_started_at         timestamptz,
    last_run_finished_at        timestamptz,
    last_success_at             timestamptz,
    minutes_since_success       double precision,
    rows_last_run               bigint,
    rows_source                 bigint,
    rows_target                 bigint,
    row_difference              bigint,
    row_difference_pct          double precision,
    source_watermark            text,
    target_watermark            text,
    source_watermark_at         timestamptz,
    target_watermark_at         timestamptz,
    replication_lag_minutes     double precision,
    freshness_status            text,
    replication_status          text,
    pipeline_status             text,
    health_status               text,
    operational_health_score    numeric(6,2),
    quality_score               numeric(6,2),
    notes                       text
);

CREATE INDEX IF NOT EXISTS ix_asset_snapshots_asset_time
    ON observability.asset_snapshots (asset_key, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS ix_asset_snapshots_time
    ON observability.asset_snapshots (snapshot_at DESC);

CREATE TABLE IF NOT EXISTS observability.quality_checks (
    quality_check_id        bigserial PRIMARY KEY,
    snapshot_id             bigint REFERENCES observability.asset_snapshots(snapshot_id) ON DELETE CASCADE,
    checked_at              timestamptz NOT NULL DEFAULT now(),
    asset_key               text NOT NULL REFERENCES observability.asset_registry(asset_key),
    check_name              text NOT NULL,
    quality_dimension       text NOT NULL,
    status                  text NOT NULL CHECK (status IN ('PASS','WARN','FAIL','SKIPPED')),
    severity                text NOT NULL DEFAULT 'warning',
    metric_value            double precision,
    threshold_value         double precision,
    details                 text
);

CREATE INDEX IF NOT EXISTS ix_quality_checks_asset_time
    ON observability.quality_checks (asset_key, checked_at DESC);
CREATE INDEX IF NOT EXISTS ix_quality_checks_status_time
    ON observability.quality_checks (status, checked_at DESC);

-- Preparación de MLOps para las páginas 3 y 4 del Control Tower.
CREATE TABLE IF NOT EXISTS model_control.scoring_batches (
    scoring_batch_id        uuid PRIMARY KEY,
    model_run_id            uuid REFERENCES model_control.model_runs(model_run_id),
    decision_system         text NOT NULL,
    model_name              text NOT NULL,
    model_version           text,
    scored_at               timestamptz NOT NULL DEFAULT now(),
    data_as_of              timestamptz,
    rows_scored             bigint NOT NULL DEFAULT 0,
    status                  text NOT NULL DEFAULT 'SUCCESS',
    drift_score             double precision,
    drift_status            text,
    metrics                 jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes                   text
);

CREATE INDEX IF NOT EXISTS ix_scoring_batches_model_time
    ON model_control.scoring_batches (model_name, scored_at DESC);

-- Una fila por activo con la observación más reciente.
CREATE OR REPLACE VIEW observability.v_asset_health_current AS
SELECT
    r.asset_key,
    r.source_schema,
    r.source_table,
    r.target_schema,
    r.target_table,
    r.layer,
    r.enabled,
    r.criticality,
    r.business_domain,
    r.business_process,
    r.business_owner,
    r.business_impact,
    r.downstream_products,
    r.expected_frequency_minutes,
    r.freshness_sla_minutes,
    r.replication_lag_sla_minutes,
    r.strategy,
    r.watermark_column,
    s.snapshot_at,
    s.mode,
    s.last_run_status,
    s.last_run_started_at,
    s.last_run_finished_at,
    s.last_success_at,
    s.minutes_since_success,
    s.rows_last_run,
    s.rows_source,
    s.rows_target,
    s.row_difference,
    s.row_difference_pct,
    s.source_watermark,
    s.target_watermark,
    s.source_watermark_at,
    s.target_watermark_at,
    s.replication_lag_minutes,
    s.freshness_status,
    s.replication_status,
    s.pipeline_status,
    s.health_status,
    s.operational_health_score,
    s.quality_score,
    s.notes
FROM observability.asset_registry r
LEFT JOIN LATERAL (
    SELECT s1.*
    FROM observability.asset_snapshots s1
    WHERE s1.asset_key = r.asset_key
    ORDER BY s1.snapshot_at DESC
    LIMIT 1
) s ON true;

CREATE OR REPLACE VIEW observability.v_pipeline_runs AS
SELECT
    r.run_id,
    r.started_at,
    r.finished_at,
    r.status,
    r.source_schema || '.' || r.source_table AS source_name,
    r.target_schema || '.' || r.target_table AS asset_key,
    r.strategy,
    r.rows_extracted,
    r.rows_loaded,
    r.watermark_before,
    r.watermark_after,
    r.error_message,
    r.host_name,
    r.process_id,
    EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - r.started_at)) / 60.0 AS duration_minutes,
    CASE WHEN r.status = 'SUCCESS' THEN 1 ELSE 0 END AS success_flag
FROM etl_control.sync_runs r;

CREATE OR REPLACE VIEW observability.v_quality_checks AS
SELECT
    q.quality_check_id,
    q.snapshot_id,
    q.checked_at,
    q.asset_key,
    a.criticality,
    a.business_process,
    a.business_impact,
    a.downstream_products,
    q.check_name,
    q.quality_dimension,
    q.status,
    q.severity,
    q.metric_value,
    q.threshold_value,
    q.details
FROM observability.quality_checks q
JOIN observability.asset_registry a USING (asset_key);

CREATE OR REPLACE VIEW observability.v_model_health_current AS
SELECT DISTINCT ON (mr.decision_system, mr.model_name)
    mr.decision_system,
    mr.model_name,
    mr.model_version,
    mr.model_run_id,
    mr.trained_at,
    mr.training_window_from,
    mr.training_window_to,
    mr.target,
    mr.status AS training_status,
    mr.metrics::text AS training_metrics_json,
    sb.scored_at AS last_scored_at,
    sb.data_as_of,
    sb.rows_scored,
    sb.status AS scoring_status,
    sb.drift_score,
    sb.drift_status,
    sb.metrics::text AS scoring_metrics_json,
    EXTRACT(EPOCH FROM (now() - mr.trained_at)) / 3600.0 AS model_age_hours,
    CASE WHEN sb.data_as_of IS NULL THEN NULL
         ELSE EXTRACT(EPOCH FROM (now() - sb.data_as_of)) / 60.0 END AS feature_freshness_minutes
FROM model_control.model_runs mr
LEFT JOIN LATERAL (
    SELECT s.*
    FROM model_control.scoring_batches s
    WHERE s.model_run_id = mr.model_run_id
       OR (s.decision_system = mr.decision_system AND s.model_name = mr.model_name)
    ORDER BY s.scored_at DESC
    LIMIT 1
) sb ON true
ORDER BY mr.decision_system, mr.model_name, mr.trained_at DESC;

CREATE OR REPLACE VIEW observability.v_decision_health_daily AS
SELECT
    date_trunc('day', r.scored_at)::date AS decision_date,
    r.decision_system,
    COUNT(*) AS recommendations,
    COUNT(a.action_id) AS actions,
    COUNT(o.outcome_id) AS outcomes,
    SUM(COALESCE(r.expected_incremental_value, 0)) AS expected_incremental_value,
    SUM(COALESCE(a.action_cost, 0)) AS action_cost,
    SUM(COALESCE(o.realized_value, 0)) AS realized_value,
    CASE WHEN COUNT(*) = 0 THEN NULL ELSE COUNT(a.action_id)::numeric / COUNT(*) END AS adoption_rate,
    CASE WHEN SUM(COALESCE(a.action_cost, 0)) = 0 THEN NULL
         ELSE (SUM(COALESCE(o.realized_value, 0)) - SUM(COALESCE(a.action_cost, 0)))
              / SUM(COALESCE(a.action_cost, 0)) END AS realized_roi
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
) o ON true
GROUP BY 1,2;

CREATE OR REPLACE VIEW observability.v_asset_quality_current AS
SELECT
    r.asset_key,
    r.criticality,
    r.business_process,
    r.business_impact,
    r.downstream_products,
    s.snapshot_at AS quality_snapshot_at,
    s.quality_score,
    s.rows_source,
    s.rows_target,
    s.row_difference,
    s.row_difference_pct
FROM observability.asset_registry r
LEFT JOIN LATERAL (
    SELECT s1.*
    FROM observability.asset_snapshots s1
    WHERE s1.asset_key = r.asset_key
      AND s1.mode = 'deep'
    ORDER BY s1.snapshot_at DESC
    LIMIT 1
) s ON true
WHERE r.enabled = true;
