-- Private Medallio research replica in Supabase.
-- This file mirrors the migration already applied to the connected project.

CREATE SCHEMA IF NOT EXISTS medallio_admin;
CREATE SCHEMA IF NOT EXISTS medallio_raw_cygnus;
CREATE SCHEMA IF NOT EXISTS medallio_raw_mercado;
CREATE SCHEMA IF NOT EXISTS medallio_staging;
CREATE SCHEMA IF NOT EXISTS medallio_core;
CREATE SCHEMA IF NOT EXISTS medallio_analytics;
CREATE SCHEMA IF NOT EXISTS medallio_etl_control;
CREATE SCHEMA IF NOT EXISTS medallio_features;
CREATE SCHEMA IF NOT EXISTS medallio_decision_intelligence;
CREATE SCHEMA IF NOT EXISTS medallio_model_control;
CREATE SCHEMA IF NOT EXISTS medallio_experiments;
CREATE SCHEMA IF NOT EXISTS medallio_observability;
CREATE SCHEMA IF NOT EXISTS medallio_research;

REVOKE ALL ON SCHEMA medallio_admin FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_raw_cygnus FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_raw_mercado FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_staging FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_core FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_analytics FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_etl_control FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_features FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_decision_intelligence FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_model_control FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_experiments FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_observability FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SCHEMA medallio_research FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS medallio_admin.sync_runs (
    sync_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    source_database text NOT NULL DEFAULT 'medallio_dw',
    sync_mode text NOT NULL,
    status text NOT NULL DEFAULT 'running',
    schemas_requested text[] NOT NULL DEFAULT '{}'::text[],
    tables_discovered integer,
    tables_completed integer NOT NULL DEFAULT 0,
    rows_copied bigint NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);

CREATE TABLE IF NOT EXISTS medallio_admin.table_registry (
    source_schema text NOT NULL,
    source_relation text NOT NULL,
    source_object_type text NOT NULL DEFAULT 'BASE TABLE',
    target_schema text NOT NULL,
    target_relation text NOT NULL,
    column_signature text,
    source_rows bigint,
    target_rows bigint,
    last_sync_run_id bigint,
    last_synced_at timestamptz,
    sync_status text,
    notes text,
    PRIMARY KEY (source_schema, source_relation)
);

CREATE TABLE IF NOT EXISTS medallio_admin.sync_table_events (
    sync_run_id bigint NOT NULL,
    source_schema text NOT NULL,
    source_relation text NOT NULL,
    target_schema text NOT NULL,
    target_relation text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    source_rows bigint,
    target_rows bigint,
    status text NOT NULL DEFAULT 'running',
    error_message text,
    PRIMARY KEY (sync_run_id, source_schema, source_relation)
);
