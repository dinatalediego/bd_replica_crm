from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg import Connection

from .models import SyncState, TableConfig

CONTROL_DDL = """
CREATE SCHEMA IF NOT EXISTS etl_control;

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
"""


def ensure_control_tables(conn: Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(CONTROL_DDL)
    conn.commit()


def get_state(conn: Connection, cfg: TableConfig) -> SyncState:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT last_watermark, watermark_data_type, rows_last_run
            FROM etl_control.sync_state
            WHERE source_schema = %s
              AND source_table = %s
              AND target_schema = %s
              AND target_table = %s
            """,
            (cfg.source_schema, cfg.source_table, cfg.target_schema, cfg.target_table),
        )
        row = cursor.fetchone()
    if not row:
        return SyncState(last_watermark=None, watermark_data_type=None, rows_last_run=0)
    return SyncState(last_watermark=row[0], watermark_data_type=row[1], rows_last_run=int(row[2] or 0))


def upsert_state(
    conn: Connection,
    cfg: TableConfig,
    watermark_data_type: str | None,
    last_watermark: str | None,
    rows_last_run: int,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO etl_control.sync_state (
                source_schema, source_table, target_schema, target_table,
                strategy, watermark_column, watermark_data_type,
                last_watermark, last_success_at, rows_last_run, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, now())
            ON CONFLICT (source_schema, source_table, target_schema, target_table)
            DO UPDATE SET
                strategy = EXCLUDED.strategy,
                watermark_column = EXCLUDED.watermark_column,
                watermark_data_type = EXCLUDED.watermark_data_type,
                last_watermark = EXCLUDED.last_watermark,
                last_success_at = EXCLUDED.last_success_at,
                rows_last_run = EXCLUDED.rows_last_run,
                updated_at = now()
            """,
            (
                cfg.source_schema,
                cfg.source_table,
                cfg.target_schema,
                cfg.target_table,
                cfg.strategy,
                cfg.watermark_column,
                watermark_data_type,
                last_watermark,
                rows_last_run,
            ),
        )
    conn.commit()


def start_run(conn: Connection, cfg: TableConfig, watermark_before: str | None) -> UUID:
    run_id = uuid4()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO etl_control.sync_runs (
                run_id, started_at, status,
                source_schema, source_table, target_schema, target_table,
                strategy, watermark_before, host_name, process_id
            )
            VALUES (%s, %s, 'RUNNING', %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                datetime.now(timezone.utc),
                cfg.source_schema,
                cfg.source_table,
                cfg.target_schema,
                cfg.target_table,
                cfg.strategy,
                watermark_before,
                socket.gethostname(),
                os.getpid(),
            ),
        )
    conn.commit()
    return run_id


def finish_run(
    conn: Connection,
    run_id: UUID,
    status: str,
    rows_extracted: int,
    rows_loaded: int,
    watermark_after: str | None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE etl_control.sync_runs
            SET finished_at = now(),
                status = %s,
                rows_extracted = %s,
                rows_loaded = %s,
                watermark_after = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (status, rows_extracted, rows_loaded, watermark_after, error_message, run_id),
        )
    conn.commit()


def try_acquire_lock(conn: Connection, cfg: TableConfig) -> bool:
    lock_name = f"{cfg.source_name}->{cfg.target_name}"
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (lock_name,))
        return bool(cursor.fetchone()[0])


def release_lock(conn: Connection, cfg: TableConfig) -> None:
    lock_name = f"{cfg.source_name}->{cfg.target_name}"
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_name,))
    conn.commit()


def recent_runs(conn: Connection, limit: int = 30) -> list[tuple]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT started_at, finished_at, status,
                   source_schema || '.' || source_table AS source_name,
                   target_schema || '.' || target_table AS target_name,
                   strategy, rows_extracted, rows_loaded,
                   watermark_before, watermark_after, error_message
            FROM etl_control.sync_runs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()
