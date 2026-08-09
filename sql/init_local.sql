-- Ejecutar conectado a PostgreSQL local como usuario con permiso para crear esquemas.
CREATE SCHEMA IF NOT EXISTS raw_cygnus;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS etl_control;
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;
CREATE SCHEMA IF NOT EXISTS model_control;
CREATE SCHEMA IF NOT EXISTS experiments;

CREATE TABLE IF NOT EXISTS etl_control.sync_state (
    source_schema       text        NOT NULL,
    source_table        text        NOT NULL,
    target_schema       text        NOT NULL,
    target_table        text        NOT NULL,
    strategy            text        NOT NULL,
    watermark_column    text,
    watermark_data_type text,
    last_watermark      text,
    last_success_at     timestamptz,
    rows_last_run       bigint      NOT NULL DEFAULT 0,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_schema, source_table, target_schema, target_table)
);

CREATE TABLE IF NOT EXISTS etl_control.sync_runs (
    run_id              uuid        PRIMARY KEY,
    started_at          timestamptz NOT NULL,
    finished_at         timestamptz,
    status              text        NOT NULL,
    source_schema       text        NOT NULL,
    source_table        text        NOT NULL,
    target_schema       text        NOT NULL,
    target_table        text        NOT NULL,
    strategy            text        NOT NULL,
    rows_extracted      bigint      NOT NULL DEFAULT 0,
    rows_loaded         bigint      NOT NULL DEFAULT 0,
    watermark_before    text,
    watermark_after     text,
    error_message       text,
    host_name           text,
    process_id          integer
);

CREATE INDEX IF NOT EXISTS ix_sync_runs_started_at
    ON etl_control.sync_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS ix_sync_runs_table
    ON etl_control.sync_runs (source_schema, source_table, started_at DESC);
