from __future__ import annotations

import hashlib
import logging

from psycopg import Connection, sql

from .errors import SchemaError
from .models import SourceColumn, TableConfig
from .type_mapping import postgres_type

LOGGER = logging.getLogger(__name__)

ETL_COLUMNS = {
    "_etl_loaded_at": "timestamp with time zone NOT NULL DEFAULT now()",
    "_etl_source_run_id": "uuid",
}


def _target_identifier(cfg: TableConfig):
    return sql.Identifier(cfg.target_schema, cfg.target_table)


def target_exists(conn: Connection, cfg: TableConfig) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
            """,
            (cfg.target_schema, cfg.target_table),
        )
        return bool(cursor.fetchone()[0])


def get_target_columns(conn: Connection, cfg: TableConfig) -> dict[str, str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (cfg.target_schema, cfg.target_table),
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


def ensure_target_table(conn: Connection, cfg: TableConfig, source_columns: list[SourceColumn]) -> None:
    if not source_columns:
        raise SchemaError(f"{cfg.source_name} no tiene columnas visibles.")

    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(cfg.target_schema)))

        definitions: list[sql.Composed] = []
        for column in source_columns:
            mapped = postgres_type(column, cfg.column_type_overrides.get(column.name))
            definitions.append(sql.SQL("{} {}").format(sql.Identifier(column.name), sql.SQL(mapped)))
        if cfg.add_etl_columns:
            for name, definition in ETL_COLUMNS.items():
                definitions.append(sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(definition)))

        if not target_exists(conn, cfg):
            if not cfg.create_target_if_missing:
                raise SchemaError(f"No existe {cfg.target_name} y create_target_if_missing=false.")
            cursor.execute(
                sql.SQL("CREATE TABLE {} ({})").format(
                    _target_identifier(cfg),
                    sql.SQL(", ").join(definitions),
                )
            )
            LOGGER.info("Tabla local creada: %s", cfg.target_name)
    conn.commit()

    existing = get_target_columns(conn, cfg)
    with conn.cursor() as cursor:
        for column in source_columns:
            if column.name not in existing:
                mapped = postgres_type(column, cfg.column_type_overrides.get(column.name))
                cursor.execute(
                    sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                        _target_identifier(cfg),
                        sql.Identifier(column.name),
                        sql.SQL(mapped),
                    )
                )
                LOGGER.warning("Columna nueva agregada en destino: %s.%s", cfg.target_name, column.name)
        if cfg.add_etl_columns:
            for name, definition in ETL_COLUMNS.items():
                if name not in existing:
                    cursor.execute(
                        sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                            _target_identifier(cfg), sql.Identifier(name), sql.SQL(definition)
                        )
                    )
    conn.commit()

    if cfg.key_columns and cfg.strategy == "incremental":
        _ensure_unique_index(conn, cfg)


def _ensure_unique_index(conn: Connection, cfg: TableConfig) -> None:
    # La llave forma parte del nombre del índice. Esto permite cambiar key_columns
    # después de una prueba sin reutilizar silenciosamente un índice de una llave anterior.
    signature = f"{cfg.target_name}|{'|'.join(cfg.key_columns)}"
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
    index_name = f"ux_replica_{digest}"
    columns = sql.SQL(", ").join(sql.Identifier(name) for name in cfg.key_columns)

    try:
        with conn.cursor() as cursor:
            # Elimina únicamente índices gestionados por esta réplica (prefijo ux_replica_)
            # que hayan quedado obsoletos para la misma tabla.
            cursor.execute(
                """
                SELECT i.relname
                FROM pg_class t
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_index ix ON ix.indrelid = t.oid
                JOIN pg_class i ON i.oid = ix.indexrelid
                WHERE n.nspname = %s
                  AND t.relname = %s
                  AND ix.indisunique
                  AND i.relname LIKE 'ux_replica_%%'
                """,
                (cfg.target_schema, cfg.target_table),
            )
            managed_indexes = [row[0] for row in cursor.fetchall()]
            for existing_name in managed_indexes:
                if existing_name != index_name:
                    cursor.execute(
                        sql.SQL("DROP INDEX IF EXISTS {}.{}").format(
                            sql.Identifier(cfg.target_schema),
                            sql.Identifier(existing_name),
                        )
                    )
                    LOGGER.warning(
                        "Índice de réplica obsoleto eliminado para %s: %s",
                        cfg.target_name,
                        existing_name,
                    )

            cursor.execute(
                sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({})").format(
                    sql.Identifier(index_name),
                    _target_identifier(cfg),
                    columns,
                )
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise SchemaError(
            f"No se pudo crear el índice único para {cfg.target_name} con {cfg.key_columns}. "
            "Puede haber duplicados o la llave configurada no es correcta."
        ) from exc


def validate_config_columns(cfg: TableConfig, source_columns: list[SourceColumn]) -> None:
    names = {column.name for column in source_columns}
    if cfg.add_etl_columns:
        collisions = sorted(names.intersection(ETL_COLUMNS))
        if collisions:
            raise SchemaError(
                f"{cfg.source_name}: columnas reservadas para control ETL ya existen: {collisions}"
            )
    missing_keys = [column for column in cfg.key_columns if column not in names]
    if missing_keys:
        raise SchemaError(f"{cfg.source_name}: key_columns inexistentes: {missing_keys}")
    if cfg.watermark_column and cfg.watermark_column not in names:
        raise SchemaError(
            f"{cfg.source_name}: watermark_column inexistente: {cfg.watermark_column}"
        )
