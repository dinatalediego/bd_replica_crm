from __future__ import annotations

import json
import logging
from typing import Iterable, Sequence
from uuid import UUID

from psycopg import Connection, sql

from .catalog import get_source_columns
from .errors import SchemaError, SyncError
from .metadata import (
    finish_run,
    get_state,
    release_lock,
    start_run,
    try_acquire_lock,
    upsert_state,
)
from .models import SourceColumn, SyncResult, SyncState, TableConfig
from .query_builder import (
    build_source_query,
    deserialize_watermark,
    serialize_watermark,
)
from .target_schema import ensure_target_table, validate_config_columns
from .type_mapping import postgres_type

LOGGER = logging.getLogger(__name__)


def _stage_name(cfg: TableConfig, run_id: UUID) -> str:
    base = f"stage_{cfg.target_table}_{str(run_id).replace('-', '')[:10]}"
    return base[:63]


def _target(cfg: TableConfig):
    return sql.Identifier(cfg.target_schema, cfg.target_table)


def _create_stage(conn: Connection, cfg: TableConfig, stage_name: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(stage_name)))
        cursor.execute(
            sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS").format(
                sql.Identifier(stage_name),
                _target(cfg),
            )
        )
    conn.commit()


def _normalize_value(value: object, column: SourceColumn, cfg: TableConfig) -> object:
    if value is None:
        return None
    mapped = postgres_type(column, cfg.column_type_overrides.get(column.name)).lower()
    if mapped == "text" or mapped.startswith("varchar") or mapped.startswith("char"):
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)
    if mapped == "bytea" and isinstance(value, memoryview):
        return value.tobytes()
    return value


def _validate_batch_keys(rows: Sequence[Sequence[object]], cfg: TableConfig, columns: list[SourceColumn]) -> None:
    if cfg.strategy != "incremental":
        return
    indexes = {column.name: index for index, column in enumerate(columns)}
    for row_number, row in enumerate(rows, start=1):
        missing = [name for name in cfg.key_columns if row[indexes[name]] is None]
        if missing:
            raise SyncError(
                f"{cfg.source_name}: fila del lote #{row_number} tiene llave nula en {missing}. "
                "Corrige key_columns o usa otra estrategia."
            )


def _copy_rows(
    conn: Connection,
    stage_name: str,
    cfg: TableConfig,
    columns: list[SourceColumn],
    rows: Sequence[Sequence[object]],
    truncate_first: bool,
) -> None:
    if not rows:
        return
    column_list = sql.SQL(", ").join(sql.Identifier(column.name) for column in columns)
    with conn.cursor() as cursor:
        if truncate_first:
            cursor.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(stage_name)))
        copy_statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(stage_name),
            column_list,
        )
        with cursor.copy(copy_statement) as copy:
            for row in rows:
                normalized = [
                    _normalize_value(value, column, cfg)
                    for value, column in zip(row, columns, strict=True)
                ]
                copy.write_row(normalized)
    conn.commit()


def _source_insert_parts(cfg: TableConfig, columns: list[SourceColumn], run_id: UUID):
    source_names = [column.name for column in columns]
    insert_names = list(source_names)
    select_parts: list[sql.Composable] = [sql.Identifier(name) for name in source_names]
    params: list[object] = []
    if cfg.add_etl_columns:
        insert_names.extend(["_etl_loaded_at", "_etl_source_run_id"])
        select_parts.extend([sql.SQL("now()"), sql.Placeholder()])
        params.append(run_id)
    return insert_names, select_parts, params


def _merge_incremental(
    conn: Connection,
    cfg: TableConfig,
    columns: list[SourceColumn],
    stage_name: str,
    run_id: UUID,
) -> int:
    source_names = [column.name for column in columns]
    insert_names, select_parts, params = _source_insert_parts(cfg, columns, run_id)

    key_sql = sql.SQL(", ").join(sql.Identifier(name) for name in cfg.key_columns)
    source_cols_sql = sql.SQL(", ").join(sql.Identifier(name) for name in source_names)
    order_parts: list[sql.Composable] = [sql.Identifier(name) for name in cfg.key_columns]
    if cfg.watermark_column:
        order_parts.append(
            sql.SQL("{} DESC NULLS LAST").format(sql.Identifier(cfg.watermark_column))
        )

    update_parts: list[sql.Composable] = []
    for name in source_names:
        if name not in cfg.key_columns:
            update_parts.append(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
            )
    if cfg.add_etl_columns:
        update_parts.extend(
            [
                sql.SQL("{} = now()").format(sql.Identifier("_etl_loaded_at")),
                sql.SQL("{} = EXCLUDED.{}").format(
                    sql.Identifier("_etl_source_run_id"),
                    sql.Identifier("_etl_source_run_id"),
                ),
            ]
        )
    if not update_parts:
        update_parts.append(
            sql.SQL("{} = EXCLUDED.{}").format(
                sql.Identifier(cfg.key_columns[0]), sql.Identifier(cfg.key_columns[0])
            )
        )

    statement = sql.SQL(
        """
        INSERT INTO {} ({})
        SELECT {}
        FROM (
            SELECT DISTINCT ON ({}) {}
            FROM {}
            ORDER BY {}
        ) AS deduplicated
        ON CONFLICT ({}) DO UPDATE SET {}
        """
    ).format(
        _target(cfg),
        sql.SQL(", ").join(sql.Identifier(name) for name in insert_names),
        sql.SQL(", ").join(select_parts),
        key_sql,
        source_cols_sql,
        sql.Identifier(stage_name),
        sql.SQL(", ").join(order_parts),
        key_sql,
        sql.SQL(", ").join(update_parts),
    )
    with conn.cursor() as cursor:
        cursor.execute(statement, tuple(params))
        affected = max(cursor.rowcount, 0)
    conn.commit()
    return affected


def _merge_append(
    conn: Connection,
    cfg: TableConfig,
    columns: list[SourceColumn],
    stage_name: str,
    run_id: UUID,
) -> int:
    insert_names, select_parts, params = _source_insert_parts(cfg, columns, run_id)
    statement = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        _target(cfg),
        sql.SQL(", ").join(sql.Identifier(name) for name in insert_names),
        sql.SQL(", ").join(select_parts),
        sql.Identifier(stage_name),
    )
    with conn.cursor() as cursor:
        cursor.execute(statement, tuple(params))
        affected = max(cursor.rowcount, 0)
    conn.commit()
    return affected


def _replace_full_refresh(
    conn: Connection,
    cfg: TableConfig,
    columns: list[SourceColumn],
    stage_name: str,
    run_id: UUID,
) -> int:
    insert_names, select_parts, params = _source_insert_parts(cfg, columns, run_id)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("TRUNCATE TABLE {}").format(_target(cfg)))
            cursor.execute(
                sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                    _target(cfg),
                    sql.SQL(", ").join(sql.Identifier(name) for name in insert_names),
                    sql.SQL(", ").join(select_parts),
                    sql.Identifier(stage_name),
                ),
                tuple(params),
            )
            affected = max(cursor.rowcount, 0)
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise


def _watermark_column(columns: list[SourceColumn], cfg: TableConfig) -> SourceColumn | None:
    return next((column for column in columns if column.name == cfg.watermark_column), None)


def sync_table(
    source_conn,
    target_conn: Connection,
    cfg: TableConfig,
    max_rows: int | None = None,
    dry_run: bool = False,
) -> SyncResult:
    columns = get_source_columns(source_conn, cfg.source_schema, cfg.source_table)
    validate_config_columns(cfg, columns)

    state = get_state(target_conn, cfg)
    query, params = build_source_query(cfg, columns, state, max_rows=max_rows)
    watermark_column = _watermark_column(columns, cfg)
    watermark_type = watermark_column.data_type if watermark_column else None

    if dry_run:
        return SyncResult(
            source_name=cfg.source_name,
            target_name=cfg.target_name,
            strategy=cfg.strategy,
            rows_extracted=0,
            rows_loaded=0,
            watermark_before=state.last_watermark,
            watermark_after=state.last_watermark,
            status="DRY_RUN",
            run_id="",
            message=f"SQL: {query}\nParámetros: {params}",
        )

    ensure_target_table(target_conn, cfg, columns)

    if not try_acquire_lock(target_conn, cfg):
        raise SyncError(f"Ya existe otra ejecución activa para {cfg.source_name}.")

    run_id = start_run(target_conn, cfg, state.last_watermark)
    stage_name = _stage_name(cfg, run_id)
    rows_extracted = 0
    rows_loaded = 0
    max_watermark: object | None = deserialize_watermark(state.last_watermark, watermark_type)

    try:
        _create_stage(target_conn, cfg, stage_name)
        LOGGER.info("Inicio %s -> %s | estrategia=%s", cfg.source_name, cfg.target_name, cfg.strategy)
        LOGGER.debug("Consulta Redshift: %s | params=%s", query, params)

        with source_conn.cursor() as source_cursor:
            source_cursor.execute(query, params)
            while True:
                batch = source_cursor.fetchmany(cfg.batch_size)
                if not batch:
                    break
                _validate_batch_keys(batch, cfg, columns)
                rows_extracted += len(batch)

                if watermark_column:
                    watermark_index = watermark_column.ordinal_position - 1
                    for row in batch:
                        candidate = row[watermark_index]
                        if candidate is not None and (max_watermark is None or candidate > max_watermark):
                            max_watermark = candidate

                if cfg.strategy == "full_refresh":
                    _copy_rows(
                        target_conn,
                        stage_name,
                        cfg,
                        columns,
                        batch,
                        truncate_first=False,
                    )
                else:
                    _copy_rows(
                        target_conn,
                        stage_name,
                        cfg,
                        columns,
                        batch,
                        truncate_first=True,
                    )
                    if cfg.strategy == "incremental":
                        rows_loaded += _merge_incremental(
                            target_conn, cfg, columns, stage_name, run_id
                        )
                    elif cfg.strategy == "append":
                        rows_loaded += _merge_append(
                            target_conn, cfg, columns, stage_name, run_id
                        )

                LOGGER.info(
                    "%s | extraídas=%s cargadas=%s",
                    cfg.source_name,
                    rows_extracted,
                    rows_loaded,
                )

        if cfg.strategy == "full_refresh":
            rows_loaded = _replace_full_refresh(
                target_conn, cfg, columns, stage_name, run_id
            )

        watermark_after = serialize_watermark(max_watermark)
        upsert_state(
            target_conn,
            cfg,
            watermark_data_type=watermark_type,
            last_watermark=watermark_after,
            rows_last_run=rows_loaded,
        )
        finish_run(
            target_conn,
            run_id,
            status="SUCCESS",
            rows_extracted=rows_extracted,
            rows_loaded=rows_loaded,
            watermark_after=watermark_after,
        )
        return SyncResult(
            source_name=cfg.source_name,
            target_name=cfg.target_name,
            strategy=cfg.strategy,
            rows_extracted=rows_extracted,
            rows_loaded=rows_loaded,
            watermark_before=state.last_watermark,
            watermark_after=watermark_after,
            status="SUCCESS",
            run_id=str(run_id),
        )
    except Exception as exc:
        target_conn.rollback()
        try:
            finish_run(
                target_conn,
                run_id,
                status="FAILED",
                rows_extracted=rows_extracted,
                rows_loaded=rows_loaded,
                watermark_after=serialize_watermark(max_watermark),
                error_message=str(exc)[:4000],
            )
        except Exception:
            target_conn.rollback()
            LOGGER.exception("No se pudo registrar el fallo del run %s", run_id)
        if isinstance(exc, (SyncError, SchemaError)):
            raise
        raise SyncError(f"Falló {cfg.source_name}: {exc}") from exc
    finally:
        try:
            release_lock(target_conn, cfg)
        except Exception:
            target_conn.rollback()
            LOGGER.exception("No se pudo liberar el advisory lock de %s", cfg.source_name)


def select_configs(
    configs: Iterable[TableConfig],
    only: str | None = None,
    include_disabled: bool = False,
) -> list[TableConfig]:
    selected: list[TableConfig] = []
    for cfg in configs:
        matches = only is None or only in {cfg.source_table, cfg.source_name, cfg.target_table, cfg.target_name}
        if matches and (cfg.enabled or include_disabled):
            selected.append(cfg)
    if only and not selected:
        raise SyncError(
            f"No se encontró una tabla seleccionable con --only {only!r}. "
            "Revise config/tables.yml o use --include-disabled para una prueba explícita."
        )
    return selected
