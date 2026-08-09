from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

import yaml

from .identifiers import qualified_redshift
from .models import SourceColumn

LOGGER = logging.getLogger(__name__)


def list_source_tables(source_conn, schema_filter: str | None = None) -> list[tuple[str, str]]:
    sql = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
    """
    params: list[object] = []
    if schema_filter:
        sql += " AND table_schema = %s"
        params.append(schema_filter)
    sql += " ORDER BY table_schema, table_name"
    with source_conn.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return [(row[0], row[1]) for row in cursor.fetchall()]


def get_source_columns(source_conn, schema: str, table: str) -> list[SourceColumn]:
    sql = """
        SELECT
            column_name,
            data_type,
            ordinal_position,
            is_nullable,
            character_maximum_length,
            numeric_precision,
            numeric_scale
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
    """
    with source_conn.cursor() as cursor:
        cursor.execute(sql, (schema, table))
        rows = cursor.fetchall()
    return [
        SourceColumn(
            name=row[0],
            data_type=row[1],
            ordinal_position=int(row[2]),
            is_nullable=str(row[3]).upper() == "YES",
            character_maximum_length=row[4],
            numeric_precision=row[5],
            numeric_scale=row[6],
        )
        for row in rows
    ]


def estimate_row_count(source_conn, schema: str, table: str) -> int | None:
    # SVV_TABLE_INFO evita COUNT(*) costoso, aunque puede ser aproximado.
    try:
        with source_conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT tbl_rows
                FROM svv_table_info
                WHERE schema = %s AND table = %s
                LIMIT 1
                """,
                (schema, table),
            )
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None
    except Exception:
        LOGGER.debug("No se pudo consultar SVV_TABLE_INFO para %s.%s", schema, table, exc_info=True)
        return None


def _candidate_key(columns: list[SourceColumn]) -> list[str]:
    names = [c.name for c in columns]
    priorities = [
        "id",
        "codigo",
        "codigo_proceso",
        "codigo_cliente",
        "codigo_proforma",
        "codigo_unidad",
        "documento_cliente",
    ]
    for candidate in priorities:
        if candidate in names:
            return [candidate]
    for name in names:
        lowered = name.lower()
        if lowered == "id" or lowered.endswith("_id"):
            return [name]
    return []


def _candidate_watermark(columns: list[SourceColumn]) -> str | None:
    names = [c.name for c in columns]
    priorities = [
        "updated_at",
        "fecha_actualizacion",
        "fecha_modificacion",
        "modified_at",
        "created_at",
        "fecha_creacion",
        "fecha_asignacion",
        "fecha_inicio",
    ]
    for candidate in priorities:
        if candidate in names:
            return candidate
    for column in columns:
        if "timestamp" in column.data_type.lower() or column.data_type.lower() == "date":
            return column.name
    return None


def discover_source(
    source_conn,
    reports_dir: Path,
    config_dir: Path,
    schema_filter: str | None = None,
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    catalog_path = reports_dir / f"source_catalog_{stamp}.csv"
    generated_config_path = config_dir / "tables.generated.yml"

    catalog_rows: list[dict[str, object]] = []
    generated_tables: list[dict[str, object]] = []
    for schema, table in list_source_tables(source_conn, schema_filter):
        columns = get_source_columns(source_conn, schema, table)
        row_count = estimate_row_count(source_conn, schema, table)
        key = _candidate_key(columns)
        watermark = _candidate_watermark(columns)
        strategy = "incremental" if key and watermark else "full_refresh"
        generated_tables.append(
            {
                "source_schema": schema,
                "source_table": table,
                "target_table": table,
                "key_columns": key,
                "watermark_column": watermark,
                "strategy": strategy,
                "enabled": False,
            }
        )
        for column in columns:
            catalog_rows.append(
                {
                    "table_schema": schema,
                    "table_name": table,
                    "estimated_rows": row_count,
                    "column_name": column.name,
                    "data_type": column.data_type,
                    "ordinal_position": column.ordinal_position,
                    "is_nullable": column.is_nullable,
                    "character_maximum_length": column.character_maximum_length,
                    "numeric_precision": column.numeric_precision,
                    "numeric_scale": column.numeric_scale,
                    "candidate_key": ",".join(key),
                    "candidate_watermark": watermark or "",
                    "suggested_strategy": strategy,
                    "source_qualified": qualified_redshift(schema, table),
                }
            )

    fieldnames = list(catalog_rows[0].keys()) if catalog_rows else ["table_schema", "table_name"]
    with catalog_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(catalog_rows)

    yaml_payload = {
        "version": 1,
        "defaults": {
            "target_schema": "raw_cygnus",
            "batch_size": 5000,
            "lookback_hours": 48,
            "enabled": False,
            "create_target_if_missing": True,
            "add_etl_columns": True,
        },
        "tables": generated_tables,
    }
    generated_config_path.write_text(
        yaml.safe_dump(yaml_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return catalog_path, generated_config_path
