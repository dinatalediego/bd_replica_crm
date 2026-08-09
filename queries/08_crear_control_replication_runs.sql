-- ============================================================
-- MEDALLIO DW - TABLA DE AUDITORIA DE REPLICACIONES
-- Ejecutar una sola vez.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS medallio_control;

CREATE TABLE IF NOT EXISTS medallio_control.replication_runs (
    run_id              BIGSERIAL PRIMARY KEY,
    source_schema       TEXT NOT NULL DEFAULT 'grupocygnus',
    source_table        TEXT NOT NULL,
    target_schema       TEXT NOT NULL DEFAULT 'raw_cygnus',
    target_table        TEXT NOT NULL,

    strategy            TEXT,
    watermark_column    TEXT,

    watermark_from      TIMESTAMP,
    watermark_to        TIMESTAMP,

    filas_extraidas     BIGINT,
    filas_insertadas    BIGINT,
    filas_actualizadas  BIGINT,
    filas_local_final   BIGINT,

    inicio_sync         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fin_sync            TIMESTAMP,
    duracion_seg        NUMERIC(14,3),

    status              TEXT NOT NULL DEFAULT 'RUNNING',
    error_message       TEXT,

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_replication_runs_table_time
    ON medallio_control.replication_runs (
        target_schema,
        target_table,
        inicio_sync DESC
    );

CREATE INDEX IF NOT EXISTS ix_replication_runs_status
    ON medallio_control.replication_runs (status);
