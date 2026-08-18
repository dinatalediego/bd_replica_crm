from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from psycopg import Connection, sql

from ..models import TableConfig
from .config import AssetMonitoringConfig
from .health import classify_health


def asset_key(cfg: TableConfig) -> str:
    return cfg.target_name


def _as_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return None


def _minutes_between(newer: datetime | None, older: datetime | None) -> float | None:
    if newer is None or older is None:
        return None
    return (newer - older).total_seconds() / 60.0


def register_asset(conn: Connection, cfg: TableConfig, monitor: AssetMonitoringConfig) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO observability.asset_registry (
                asset_key, source_schema, source_table, target_schema, target_table,
                layer, enabled, criticality, business_domain, business_process,
                business_owner, business_impact, downstream_products,
                expected_frequency_minutes, freshness_sla_minutes,
                replication_lag_sla_minutes, reconciliation_tolerance_pct,
                strategy, watermark_column, key_columns,
                monitor_source_watermark, deep_quality_enabled, updated_at
            ) VALUES (
                %s,%s,%s,%s,%s,'raw',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
            )
            ON CONFLICT (asset_key) DO UPDATE SET
                source_schema = EXCLUDED.source_schema,
                source_table = EXCLUDED.source_table,
                target_schema = EXCLUDED.target_schema,
                target_table = EXCLUDED.target_table,
                enabled = EXCLUDED.enabled,
                criticality = EXCLUDED.criticality,
                business_domain = EXCLUDED.business_domain,
                business_process = EXCLUDED.business_process,
                business_owner = EXCLUDED.business_owner,
                business_impact = EXCLUDED.business_impact,
                downstream_products = EXCLUDED.downstream_products,
                expected_frequency_minutes = EXCLUDED.expected_frequency_minutes,
                freshness_sla_minutes = EXCLUDED.freshness_sla_minutes,
                replication_lag_sla_minutes = EXCLUDED.replication_lag_sla_minutes,
                reconciliation_tolerance_pct = EXCLUDED.reconciliation_tolerance_pct,
                strategy = EXCLUDED.strategy,
                watermark_column = EXCLUDED.watermark_column,
                key_columns = EXCLUDED.key_columns,
                monitor_source_watermark = EXCLUDED.monitor_source_watermark,
                deep_quality_enabled = EXCLUDED.deep_quality_enabled,
                updated_at = now()
            """,
            (
                asset_key(cfg), cfg.source_schema, cfg.source_table, cfg.target_schema,
                cfg.target_table, cfg.enabled, monitor.criticality.lower(),
                monitor.business_domain, monitor.business_process, monitor.business_owner,
                monitor.business_impact, monitor.downstream_products,
                monitor.expected_frequency_minutes, monitor.freshness_sla_minutes,
                monitor.replication_lag_sla_minutes, monitor.reconciliation_tolerance_pct,
                cfg.strategy, cfg.watermark_column, cfg.key_columns,
                monitor.monitor_source_watermark, monitor.deep_quality_enabled,
            ),
        )
    conn.commit()


def _last_run(conn: Connection, cfg: TableConfig) -> dict[str, Any]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, started_at, finished_at, rows_loaded
            FROM etl_control.sync_runs
            WHERE source_schema=%s AND source_table=%s
              AND target_schema=%s AND target_table=%s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (cfg.source_schema, cfg.source_table, cfg.target_schema, cfg.target_table),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT last_success_at, rows_last_run
            FROM etl_control.sync_state
            WHERE source_schema=%s AND source_table=%s
              AND target_schema=%s AND target_table=%s
            """,
            (cfg.source_schema, cfg.source_table, cfg.target_schema, cfg.target_table),
        )
        state = cursor.fetchone()
    return {
        "status": row[0] if row else None,
        "started_at": row[1] if row else None,
        "finished_at": row[2] if row else None,
        "rows_loaded": int(row[3] or 0) if row else 0,
        "last_success_at": state[0] if state else None,
        "rows_last_run": int(state[1] or 0) if state else 0,
    }


""" def _source_max_watermark(source_conn, cfg):
    query = (
        f'SELECT MAX("{cfg.watermark_column}") '
        f'FROM "{cfg.source_schema}"."{cfg.source_table}"'
    )

    try:
        with source_conn.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else None
    except TimeoutError:
        LOGGER.warning(
            "Timeout obteniendo watermark de origen para %s.%s; "
            "la observación continuará sin watermark de origen.",
            cfg.source_schema,
            cfg.source_table,
            exc_info=True,
        )
        return None """

def _source_max_watermark(source_conn, cfg):
    query = (
        f'SELECT MAX("{cfg.watermark_column}") '
        f'FROM "{cfg.source_schema}"."{cfg.source_table}"'
    )

    try:
        with source_conn.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as exc:
        LOGGER.warning(
            "No se pudo obtener watermark de origen para %s.%s. "
            "tipo=%s; detalle=%s. "
            "La observación continuará sin watermark de origen.",
            cfg.source_schema,
            cfg.source_table,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return None
    
def _target_table_exists(conn: Connection, cfg: TableConfig) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema=%s AND table_name=%s
            )
            """,
            (cfg.target_schema, cfg.target_table),
        )
        return bool(cursor.fetchone()[0])


def _target_max_watermark(conn: Connection, cfg: TableConfig) -> object | None:
    if not cfg.watermark_column:
        return None
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT MAX({}) FROM {}.{}").format(
                sql.Identifier(cfg.watermark_column),
                sql.Identifier(cfg.target_schema),
                sql.Identifier(cfg.target_table),
            )
        )
        return cursor.fetchone()[0]


def _source_count(source_conn, cfg: TableConfig) -> int:
    query = f'SELECT COUNT(*) FROM "{cfg.source_schema}"."{cfg.source_table}"'
    with source_conn.cursor() as cursor:
        cursor.execute(query)
        return int(cursor.fetchone()[0])


def _target_count(conn: Connection, cfg: TableConfig) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(cfg.target_schema), sql.Identifier(cfg.target_table)
            )
        )
        return int(cursor.fetchone()[0])


def _target_estimated_rows(conn: Connection, cfg: TableConfig) -> int | None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT n_live_tup::bigint
            FROM pg_stat_user_tables
            WHERE schemaname=%s AND relname=%s
            """,
            (cfg.target_schema, cfg.target_table),
        )
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None


def _null_key_count(conn: Connection, cfg: TableConfig) -> int | None:
    if not cfg.key_columns:
        return None
    condition = sql.SQL(" OR ").join(
        sql.SQL("{} IS NULL").format(sql.Identifier(k)) for k in cfg.key_columns
    )
    statement = sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE {}").format(
        sql.Identifier(cfg.target_schema), sql.Identifier(cfg.target_table), condition
    )
    with conn.cursor() as cursor:
        cursor.execute(statement)
        return int(cursor.fetchone()[0])


def _duplicate_key_groups(conn: Connection, cfg: TableConfig) -> int | None:
    if not cfg.key_columns:
        return None
    keys = sql.SQL(", ").join(sql.Identifier(k) for k in cfg.key_columns)
    statement = sql.SQL(
        "SELECT COUNT(*) FROM (SELECT {} FROM {}.{} GROUP BY {} HAVING COUNT(*) > 1) d"
    ).format(
        keys,
        sql.Identifier(cfg.target_schema),
        sql.Identifier(cfg.target_table),
        keys,
    )
    with conn.cursor() as cursor:
        cursor.execute(statement)
        return int(cursor.fetchone()[0])


def _source_columns(source_conn, cfg: TableConfig) -> set[str]:
    with source_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (cfg.source_schema, cfg.source_table),
        )
        return {row[0] for row in cursor.fetchall()}


def _target_columns(conn: Connection, cfg: TableConfig) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """,
            (cfg.target_schema, cfg.target_table),
        )
        return {row[0] for row in cursor.fetchall() if not row[0].startswith("_etl_")}


def _insert_snapshot(conn: Connection, values: dict[str, Any]) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO observability.asset_snapshots (
                mode, asset_key, last_run_status, last_run_started_at, last_run_finished_at,
                last_success_at, minutes_since_success, rows_last_run,
                rows_source, rows_target, row_difference, row_difference_pct,
                source_watermark, target_watermark, source_watermark_at, target_watermark_at,
                replication_lag_minutes, freshness_status, replication_status,
                pipeline_status, health_status, operational_health_score, quality_score, notes
            ) VALUES (
                %(mode)s, %(asset_key)s, %(last_run_status)s, %(last_run_started_at)s,
                %(last_run_finished_at)s, %(last_success_at)s, %(minutes_since_success)s,
                %(rows_last_run)s, %(rows_source)s, %(rows_target)s, %(row_difference)s,
                %(row_difference_pct)s, %(source_watermark)s, %(target_watermark)s,
                %(source_watermark_at)s, %(target_watermark_at)s, %(replication_lag_minutes)s,
                %(freshness_status)s, %(replication_status)s, %(pipeline_status)s,
                %(health_status)s, %(operational_health_score)s, %(quality_score)s, %(notes)s
            ) RETURNING snapshot_id
            """,
            values,
        )
        snapshot_id = int(cursor.fetchone()[0])
    conn.commit()
    return snapshot_id


def _check(
    conn: Connection,
    snapshot_id: int,
    key: str,
    check_name: str,
    dimension: str,
    status: str,
    severity: str,
    metric: float | None,
    threshold: float | None,
    details: str,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO observability.quality_checks (
                snapshot_id, asset_key, check_name, quality_dimension,
                status, severity, metric_value, threshold_value, details
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (snapshot_id, key, check_name, dimension, status, severity, metric, threshold, details),
        )
    conn.commit()


def collect_asset_snapshot(
    source_conn,
    target_conn: Connection,
    cfg: TableConfig,
    monitor: AssetMonitoringConfig,
    mode: str = "hourly",
) -> dict[str, Any]:
    if mode not in {"hourly", "deep"}:
        raise ValueError("mode debe ser hourly o deep")

    register_asset(target_conn, cfg, monitor)
    key = asset_key(cfg)
    now = datetime.now(timezone.utc)
    last = _last_run(target_conn, cfg)
    minutes_since_success = _minutes_between(now, _as_datetime(last["last_success_at"]))

    target_exists = _target_table_exists(target_conn, cfg)
    source_wm = None
    target_wm = None

    if monitor.monitor_source_watermark and cfg.watermark_column:
        if mode == "deep":
            source_wm = _source_max_watermark(source_conn, cfg)

        if target_exists:
            target_wm = _target_max_watermark(target_conn, cfg)

    source_wm_dt = _as_datetime(source_wm)
    target_wm_dt = _as_datetime(target_wm)
    replication_lag = _minutes_between(source_wm_dt, target_wm_dt)

    if replication_lag is not None:
        replication_lag = max(replication_lag, 0.0)

    """     target_exists = _target_table_exists(target_conn, cfg)
    source_wm = None
    target_wm = None
    if mode == "hourly":
        source_wm = None
    else:
        source_wm = _source_max_watermark(source_conn, cfg)

    source_wm_dt = _as_datetime(source_wm)
    target_wm_dt = _as_datetime(target_wm)
    replication_lag = _minutes_between(source_wm_dt, target_wm_dt)
    if replication_lag is not None:
        replication_lag = max(replication_lag, 0.0) """

    rows_source = None
    rows_target = _target_estimated_rows(target_conn, cfg) if target_exists else None
    if mode == "deep":
        rows_source = _source_count(source_conn, cfg)
        rows_target = _target_count(target_conn, cfg) if target_exists else None

    row_diff = rows_target - rows_source if rows_source is not None and rows_target is not None else None
    row_diff_pct = None
    if rows_source not in (None, 0) and row_diff is not None:
        row_diff_pct = abs(row_diff) / rows_source * 100.0

    health = classify_health(
        minutes_since_success=minutes_since_success,
        freshness_sla_minutes=monitor.freshness_sla_minutes,
        replication_lag_minutes=replication_lag,
        replication_lag_sla_minutes=monitor.replication_lag_sla_minutes,
        last_run_status=last["status"],
    )

    values = {
        "mode": mode,
        "asset_key": key,
        "last_run_status": last["status"],
        "last_run_started_at": last["started_at"],
        "last_run_finished_at": last["finished_at"],
        "last_success_at": last["last_success_at"],
        "minutes_since_success": minutes_since_success,
        "rows_last_run": last["rows_last_run"],
        "rows_source": rows_source,
        "rows_target": rows_target,
        "row_difference": row_diff,
        "row_difference_pct": row_diff_pct,
        "source_watermark": None if source_wm is None else str(source_wm),
        "target_watermark": None if target_wm is None else str(target_wm),
        "source_watermark_at": source_wm_dt,
        "target_watermark_at": target_wm_dt,
        "replication_lag_minutes": replication_lag,
        "freshness_status": health.freshness_status,
        "replication_status": health.replication_status,
        "pipeline_status": health.pipeline_status,
        "health_status": health.health_status,
        "operational_health_score": health.score,
        "quality_score": None,
        "notes": None,
    }
    snapshot_id = _insert_snapshot(target_conn, values)

    _check(
        target_conn, snapshot_id, key, "freshness_sla", "freshness",
        "PASS" if health.freshness_status == "OK" else "WARN" if health.freshness_status == "WARN" else "FAIL" if health.freshness_status == "FAIL" else "SKIPPED",
        "critical" if monitor.criticality.lower() == "critical" else "warning",
        minutes_since_success, float(monitor.freshness_sla_minutes),
        "Minutos transcurridos desde la última sincronización exitosa.",
    )
    _check(
        target_conn, snapshot_id, key, "replication_lag", "reconciliation",
        "PASS" if health.replication_status == "OK" else "WARN" if health.replication_status == "WARN" else "FAIL" if health.replication_status == "FAIL" else "SKIPPED",
        "critical" if monitor.criticality.lower() == "critical" else "warning",
        replication_lag, float(monitor.replication_lag_sla_minutes),
        "Diferencia entre MAX(watermark) de Redshift y PostgreSQL.",
    )
    _check(
        target_conn, snapshot_id, key, "last_pipeline_run", "availability",
        "PASS" if health.pipeline_status in {"OK", "RUNNING"} else "FAIL" if health.pipeline_status == "FAIL" else "SKIPPED",
        "critical" if monitor.criticality.lower() == "critical" else "warning",
        1.0 if health.pipeline_status in {"OK", "RUNNING"} else 0.0,
        1.0,
        f"Último estado del pipeline: {last['status'] or 'sin ejecución'}.",
    )
    _check(
        target_conn, snapshot_id, key, "target_table_exists", "availability",
        "PASS" if target_exists else "FAIL",
        "critical" if monitor.criticality.lower() == "critical" else "warning",
        1.0 if target_exists else 0.0, 1.0,
        "La tabla destino existe en PostgreSQL." if target_exists else "La tabla destino aún no existe; revisar primer sync/configuración.",
    )

    quality_score = None
    if mode == "deep" and monitor.deep_quality_enabled:
        checks: list[tuple[str, bool]] = []
        if not target_exists:
            checks.append(("target_table_exists", False))

        if row_diff_pct is not None:
            passed = row_diff_pct <= monitor.reconciliation_tolerance_pct
            checks.append(("reconciliation_count", passed))
            _check(
                target_conn, snapshot_id, key, "row_count_reconciliation", "reconciliation",
                "PASS" if passed else "FAIL",
                "critical" if monitor.criticality.lower() == "critical" else "warning",
                row_diff_pct, monitor.reconciliation_tolerance_pct,
                f"Origen={rows_source}; destino={rows_target}; diferencia={row_diff}.",
            )

        null_keys = _null_key_count(target_conn, cfg) if target_exists else None
        if null_keys is not None:
            passed = null_keys == 0
            checks.append(("null_keys", passed))
            _check(
                target_conn, snapshot_id, key, "null_business_key", "completeness",
                "PASS" if passed else "FAIL", "critical", float(null_keys), 0.0,
                "Filas con al menos una columna de key_columns en NULL.",
            )

        duplicate_groups = _duplicate_key_groups(target_conn, cfg) if target_exists else None
        if duplicate_groups is not None:
            passed = duplicate_groups == 0
            checks.append(("duplicate_keys", passed))
            _check(
                target_conn, snapshot_id, key, "duplicate_business_key", "uniqueness",
                "PASS" if passed else "FAIL", "critical", float(duplicate_groups), 0.0,
                "Grupos de key_columns duplicados en PostgreSQL local.",
            )

        missing_columns = sorted(_source_columns(source_conn, cfg) - _target_columns(target_conn, cfg)) if target_exists else sorted(_source_columns(source_conn, cfg))
        passed = not missing_columns
        checks.append(("schema_drift", passed))
        _check(
            target_conn, snapshot_id, key, "schema_drift", "schema",
            "PASS" if passed else "FAIL", "critical", float(len(missing_columns)), 0.0,
            "Sin columnas faltantes." if passed else "Faltan en destino: " + ", ".join(missing_columns),
        )

        quality_score = round(100.0 * sum(1 for _, ok in checks if ok) / len(checks), 2) if checks else None
        with target_conn.cursor() as cursor:
            cursor.execute(
                "UPDATE observability.asset_snapshots SET quality_score=%s WHERE snapshot_id=%s",
                (quality_score, snapshot_id),
            )
        target_conn.commit()

    return {
        "asset_key": key,
        "snapshot_id": snapshot_id,
        "mode": mode,
        "health_status": health.health_status,
        "operational_health_score": health.score,
        "quality_score": quality_score,
        "replication_lag_minutes": replication_lag,
        "minutes_since_success": minutes_since_success,
    }
