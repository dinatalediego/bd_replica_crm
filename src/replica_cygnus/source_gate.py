"""Scheduling and Watch use only the existing PostgreSQL replication ledger."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .config import load_table_configs
from .connections import connect_postgres
from .metadata import ensure_control_tables
from .errors import ConfigurationError


def merged_configs(primary: Path, additional: tuple[Path, ...] = ()):
    # The local configuration wins, including explicit disabled tables.
    result = {}
    for path in (primary, *additional):
        for cfg in load_table_configs(path):
            key = (cfg.source_schema, cfg.source_table, cfg.target_schema, cfg.target_table)
            result.setdefault(key, cfg)
    return list(result.values())


def interval_hours(cfg) -> float:
    variable = "REDSHIFT_FULL_SYNC_INTERVAL_HOURS" if cfg.strategy == "full_refresh" else "REDSHIFT_SYNC_INTERVAL_HOURS"
    value = float(os.getenv(variable, "24" if cfg.strategy == "full_refresh" else "4"))
    if not 1 <= value <= 8760:
        raise ConfigurationError(f"{variable} debe estar entre 1 y 8760 horas.")
    return value


def ledger(conn, cfg):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT s.last_success_at, s.last_watermark, s.rows_last_run,
                   r.started_at, r.status, r.error_message
            FROM (SELECT 1) seed
            LEFT JOIN etl_control.sync_state s ON
              s.source_schema=%s AND s.source_table=%s AND s.target_schema=%s AND s.target_table=%s
            LEFT JOIN LATERAL (
              SELECT started_at, status, error_message FROM etl_control.sync_runs
              WHERE source_schema=%s AND source_table=%s AND target_schema=%s AND target_table=%s
              ORDER BY started_at DESC LIMIT 1
            ) r ON true
        """, (cfg.source_schema, cfg.source_table, cfg.target_schema, cfg.target_table) * 2)
        return cursor.fetchone()


def age_minutes(last_success, now):
    if last_success is None:
        return None
    if last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=timezone.utc)
    return (now - last_success).total_seconds() / 60


def is_due(cfg, last_success, now):
    age = age_minutes(last_success, now)
    return age is None or age >= interval_hours(cfg) * 60


def due_configs(conn, configs, now=None):
    now = now or datetime.now(timezone.utc)
    return [cfg for cfg in configs if is_due(cfg, ledger(conn, cfg)[0], now)]


def watch_rows(settings, primary, additional=()):
    now = datetime.now(timezone.utc)
    rows = []
    with connect_postgres(settings) as conn:
        ensure_control_tables(conn)
        for cfg in merged_configs(primary, additional):
            if not cfg.enabled:
                continue
            last, watermark, count, attempt, status, error = ledger(conn, cfg)
            age = age_minutes(last, now)
            health = "SIN_REPLICA" if last is None else "VENCIDA" if is_due(cfg, last, now) else "AL_DIA"
            if status in {"FAILED", "RUNNING"}:
                health = status
            rows.append((cfg.source_name, last, None if age is None else round(age, 1), interval_hours(cfg), health, watermark, count, attempt, error))
    return rows
