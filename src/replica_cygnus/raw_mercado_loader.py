from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2 import sql


@dataclass
class MercadoLoadResult:
    run_id: int | None
    source_file: str
    source_sha256: str
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    snapshot_table: str | None
    status: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_column(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip().lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _read_csv(path: Path, delimiter: str = ",", encoding: str = "utf-8-sig") -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding=encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("El CSV no contiene cabecera.")
        headers = [_normalize_column(h) for h in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValueError("La cabecera genera columnas duplicadas después de normalizar nombres.")
        rows: list[dict[str, str]] = []
        for raw in reader:
            normalized = {headers[i]: (raw.get(reader.fieldnames[i]) or "").strip() for i in range(len(headers))}
            if any(v != "" for v in normalized.values()):
                rows.append(normalized)
    return headers, rows


def _ensure_control_tables(cur) -> None:
    cur.execute("CREATE SCHEMA IF NOT EXISTS etl_control")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_control.raw_mercado_load_runs (
            run_id BIGSERIAL PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            source_file TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            source_row_count INTEGER,
            loaded_row_count INTEGER,
            rejected_row_count INTEGER,
            target_schema TEXT NOT NULL DEFAULT 'raw_mercado',
            target_table TEXT NOT NULL DEFAULT 'unidades',
            snapshot_table TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            error_message TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )


def _start_control_run(
    database_url: str,
    *,
    source_file: str,
    source_sha256: str,
    source_row_count: int,
    schema_name: str,
    table_name: str,
    delimiter: str,
    encoding: str,
    source_run_id: str,
) -> int | None:
    """Best-effort audit logging. A permission problem must not block the data load."""
    control_conn = None
    try:
        control_conn = psycopg2.connect(database_url)
        control_conn.autocommit = True
        with control_conn.cursor() as cur:
            _ensure_control_tables(cur)
            cur.execute(
                """
                INSERT INTO etl_control.raw_mercado_load_runs
                    (source_file, source_sha256, source_row_count, target_schema, target_table, metadata)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING run_id
                """,
                (
                    source_file,
                    source_sha256,
                    source_row_count,
                    schema_name,
                    table_name,
                    json.dumps(
                        {
                            "delimiter": delimiter,
                            "encoding": encoding,
                            "source_run_id": source_run_id,
                        }
                    ),
                ),
            )
            return int(cur.fetchone()[0])
    except psycopg2.Error:
        return None
    finally:
        if control_conn is not None:
            control_conn.close()


def _finish_control_run(
    database_url: str,
    run_id: int | None,
    *,
    status: str,
    loaded_row_count: int | None = None,
    rejected_row_count: int | None = None,
    snapshot_table: str | None = None,
    error_message: str | None = None,
) -> None:
    if run_id is None:
        return
    control_conn = None
    try:
        control_conn = psycopg2.connect(database_url)
        control_conn.autocommit = True
        with control_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE etl_control.raw_mercado_load_runs
                   SET finished_at = now(),
                       loaded_row_count = COALESCE(%s, loaded_row_count),
                       rejected_row_count = COALESCE(%s, rejected_row_count),
                       snapshot_table = COALESCE(%s, snapshot_table),
                       status = %s,
                       error_message = %s
                 WHERE run_id = %s
                """,
                (
                    loaded_row_count,
                    rejected_row_count,
                    snapshot_table,
                    status,
                    error_message,
                    run_id,
                ),
            )
    except psycopg2.Error:
        pass
    finally:
        if control_conn is not None:
            control_conn.close()


def _ensure_target(cur, columns: Iterable[str], schema_name: str, table_name: str) -> None:
    cur.execute("SELECT to_regclass(%s)", (f"{schema_name}.{table_name}",))
    relation = cur.fetchone()[0]

    if relation is None:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name)))
        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ()").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
        )
        for col in columns:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} TEXT").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name), sql.Identifier(col)
                )
            )
        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ADD COLUMN _etl_source_run_id UUID NOT NULL").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ADD COLUMN _source_file TEXT").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ADD COLUMN _source_sha256 TEXT").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ADD COLUMN _loaded_at TIMESTAMPTZ DEFAULT now()").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
        )
        return

    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = %s
           AND table_name = %s
        """,
        (schema_name, table_name),
    )
    target_columns = {row[0] for row in cur.fetchall()}
    required = set(columns) | {"_etl_source_run_id", "_source_file", "_source_sha256"}
    missing = sorted(required - target_columns)
    if missing:
        raise RuntimeError(
            f"La tabla {schema_name}.{table_name} existe pero faltan columnas requeridas: {', '.join(missing)}"
        )


def load_raw_mercado(
    database_url: str,
    file_path: str,
    *,
    schema_name: str = "raw_mercado",
    table_name: str = "unidades",
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    snapshot: bool = True,
    replace: bool = True,
) -> MercadoLoadResult:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError("Por ahora el loader acepta archivos CSV.")

    source_hash = _sha256(path)
    source_run_id = str(uuid.uuid4())
    headers, rows = _read_csv(path, delimiter=delimiter, encoding=encoding)
    if not rows:
        raise ValueError("El archivo no contiene filas de datos.")

    run_id = _start_control_run(
        database_url,
        source_file=str(path),
        source_sha256=source_hash,
        source_row_count=len(rows),
        schema_name=schema_name,
        table_name=table_name,
        delimiter=delimiter,
        encoding=encoding,
        source_run_id=source_run_id,
    )

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    snapshot_table: str | None = None
    loaded = 0
    try:
        with conn.cursor() as cur:
            _ensure_target(cur, headers, schema_name, table_name)

            if snapshot:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                suffix = str(run_id) if run_id is not None else source_run_id.replace("-", "")[:12]
                snapshot_table = f"{table_name}_snapshot_{stamp}_{suffix}"
                cur.execute(
                    sql.SQL("CREATE TABLE {}.{} AS TABLE {}.{}")
                    .format(
                        sql.Identifier(schema_name), sql.Identifier(snapshot_table),
                        sql.Identifier(schema_name), sql.Identifier(table_name),
                    )
                )

            if replace:
                cur.execute(
                    sql.SQL("TRUNCATE TABLE {}.{}").format(
                        sql.Identifier(schema_name), sql.Identifier(table_name)
                    )
                )

            insert_columns = headers + ["_etl_source_run_id", "_source_file", "_source_sha256"]
            query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
                sql.SQL(", ").join(sql.Placeholder() * len(insert_columns)),
            )
            payload = [
                tuple(row[h] for h in headers) + (source_run_id, str(path), source_hash)
                for row in rows
            ]
            cur.executemany(query, payload)

            cur.execute(
                sql.SQL("SELECT count(*) FROM {}.{} WHERE _source_sha256 = %s").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name)
                ),
                (source_hash,),
            )
            loaded = int(cur.fetchone()[0])
            if loaded != len(rows):
                raise RuntimeError(f"QA falló: se leyeron {len(rows)} filas pero quedaron {loaded} filas de esta carga.")

        conn.commit()
        _finish_control_run(
            database_url,
            run_id,
            status="success",
            loaded_row_count=loaded,
            rejected_row_count=0,
            snapshot_table=snapshot_table,
        )
        return MercadoLoadResult(
            run_id=run_id,
            source_file=str(path),
            source_sha256=source_hash,
            rows_read=len(rows),
            rows_loaded=loaded,
            rows_rejected=0,
            snapshot_table=snapshot_table,
            status="success",
        )
    except Exception as exc:
        conn.rollback()
        _finish_control_run(
            database_url,
            run_id,
            status="failed",
            loaded_row_count=0,
            error_message=str(exc),
        )
        raise
    finally:
        conn.close()
