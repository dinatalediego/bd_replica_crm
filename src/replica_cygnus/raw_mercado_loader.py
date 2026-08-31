from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


SOURCE_TO_TARGET = {
    "codigo_unidad": "codigo",
    "tipologia": "nombre_tipologia",
    "dormitorios": "total_habitaciones",
    "area_venta": "area_total",
    "estado": "estado_comercial",
    "precio_lista": "precio_lista",
    "precio_venta": "precio_venta",
    "pxm2": "precio_m2",
    "fecha_separacion": "fecha_separacion",
    "fecha_venta": "fecha_venta",
    "area_techada": "area_techada",
    "area_libre": "area_libre",
    "piso": "piso",
    "tipo_unidad": "tipo_unidad",
}

REQUIRED_TARGET_COLUMNS = {"codigo", "codigo_proyecto", "id", "_etl_source_run_id"}


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
            normalized = {
                headers[i]: (raw.get(reader.fieldnames[i]) or "").strip()
                for i in range(len(headers))
            }
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


def _get_target_columns(cur, schema_name: str, table_name: str) -> list[str]:
    cur.execute("SELECT to_regclass(%s)", (f"{schema_name}.{table_name}",))
    if cur.fetchone()[0] is None:
        raise RuntimeError(
            f"La tabla destino {schema_name}.{table_name} no existe. "
            "Este loader requiere el contrato canónico ya creado."
        )

    cur.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = %s
           AND table_name = %s
         ORDER BY ordinal_position
        """,
        (schema_name, table_name),
    )
    columns = [row[0] for row in cur.fetchall()]
    missing = sorted(REQUIRED_TARGET_COLUMNS - set(columns))
    if missing:
        raise RuntimeError(
            f"El contrato de {schema_name}.{table_name} no contiene columnas obligatorias: {', '.join(missing)}"
        )
    return columns


def _blank_to_none(value: str | None):
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _build_canonical_rows(
    rows: list[dict[str, str]],
    target_columns: list[str],
    source_run_id: str,
) -> tuple[list[str], list[tuple]]:
    target_set = set(target_columns)

    insert_columns: list[str] = []
    for column in target_columns:
        if column in {"_etl_loaded_at", "_etl_source_run_id"}:
            continue
        if any(column in row and row[column] != "" for row in rows):
            insert_columns.append(column)
            continue
        if any(target == column and source in rows[0] for source, target in SOURCE_TO_TARGET.items()):
            insert_columns.append(column)

    for required in ("codigo", "codigo_proyecto", "id"):
        if required not in insert_columns:
            insert_columns.append(required)
    insert_columns.append("_etl_source_run_id")

    unknown = set(insert_columns) - target_set
    if unknown:
        raise RuntimeError(f"Columnas de inserción fuera del contrato: {', '.join(sorted(unknown))}")

    payload: list[tuple] = []
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()

    for index, row in enumerate(rows, start=1):
        canonical: dict[str, object] = {}

        for column in target_columns:
            if column in row:
                canonical[column] = _blank_to_none(row[column])

        for source, target in SOURCE_TO_TARGET.items():
            if target not in canonical or canonical[target] is None:
                if source in row:
                    canonical[target] = _blank_to_none(row[source])

        canonical["codigo"] = canonical.get("codigo") or _blank_to_none(row.get("codigo_unidad"))
        canonical["codigo_proyecto"] = canonical.get("codigo_proyecto") or "Amma-TM"
        canonical["id"] = canonical.get("id") or _blank_to_none(row.get("id"))
        canonical["_etl_source_run_id"] = source_run_id

        missing_required = [
            col for col in ("codigo", "codigo_proyecto", "id")
            if canonical.get(col) in (None, "")
        ]
        if missing_required:
            raise ValueError(
                f"Fila {index}: faltan campos obligatorios: {', '.join(missing_required)}"
            )

        code = str(canonical["codigo"])
        row_id = str(canonical["id"])
        if code in seen_codes:
            raise ValueError(f"Fila {index}: codigo duplicado en el CSV: {code}")
        if row_id in seen_ids:
            raise ValueError(f"Fila {index}: id duplicado en el CSV: {row_id}")
        seen_codes.add(code)
        seen_ids.add(row_id)

        payload.append(tuple(canonical.get(column) for column in insert_columns))

    return insert_columns, payload


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
    _, rows = _read_csv(path, delimiter=delimiter, encoding=encoding)
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
            target_columns = _get_target_columns(cur, schema_name, table_name)
            insert_columns, payload = _build_canonical_rows(rows, target_columns, source_run_id)

            if snapshot:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                suffix = str(run_id) if run_id is not None else source_run_id.replace("-", "")[:12]
                snapshot_table = f"{table_name}_snapshot_{stamp}_{suffix}"
                cur.execute(
                    sql.SQL("CREATE TABLE {}.{} AS TABLE {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(snapshot_table),
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name),
                    )
                )

            if replace:
                cur.execute(
                    sql.SQL("TRUNCATE TABLE {}.{}").format(
                        sql.Identifier(schema_name), sql.Identifier(table_name)
                    )
                )

            query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
                sql.SQL(", ").join(sql.Placeholder() * len(insert_columns)),
            )
            cur.executemany(query, payload)

            cur.execute(
                sql.SQL(
                    "SELECT count(*), count(DISTINCT codigo), count(DISTINCT _etl_source_run_id) "
                    "FROM {}.{} WHERE _etl_source_run_id = %s::uuid"
                ).format(sql.Identifier(schema_name), sql.Identifier(table_name)),
                (source_run_id,),
            )
            loaded, distinct_codes, distinct_runs = map(int, cur.fetchone())
            if loaded != len(rows):
                raise RuntimeError(
                    f"QA falló: se leyeron {len(rows)} filas pero se cargaron {loaded}."
                )
            if distinct_codes != len(rows):
                raise RuntimeError(
                    f"QA falló: {loaded} filas cargadas pero solo {distinct_codes} códigos distintos."
                )
            if distinct_runs != 1:
                raise RuntimeError("QA falló: la carga no quedó asociada a un único _etl_source_run_id.")

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
