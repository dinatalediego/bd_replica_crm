from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pandas as pd
if TYPE_CHECKING:
    from psycopg import Connection

from .config import MarketSource


EXPECTED_COLUMNS = [
    "codigo_unidad", "torre", "tipo_unidad", "tipologia", "nro_inmueble",
    "piso", "vista", "area_techada", "area_libre", "area_venta",
    "dormitorios", "moneda", "precio_lista", "precio_venta", "pxm2",
    "fecha_separacion", "fecha_venta", "estado",
    "estado_comercial_original", "referido",
]

RENAME_COLUMNS = {
    "nro_inmueble": "numero_inmueble",
    "area_techada": "area_techada_m2",
    "area_libre": "area_libre_m2",
    "area_venta": "area_venta_m2",
    "pxm2": "precio_m2",
    "estado": "estado_comercial",
}

TEXT_COLUMNS = [
    "codigo_unidad", "torre", "tipo_unidad", "tipologia", "numero_inmueble",
    "vista", "moneda", "estado_comercial", "estado_comercial_original", "referido",
]
NUMERIC_COLUMNS = [
    "area_techada_m2", "area_libre_m2", "area_venta_m2",
    "precio_lista", "precio_venta", "precio_m2",
]
INTEGER_COLUMNS = ["piso", "dormitorios"]
DATE_COLUMNS = ["fecha_separacion", "fecha_venta"]


@dataclass(frozen=True)
class PreparedMarketData:
    frame: pd.DataFrame
    warnings: list[str]
    file_hash: str


class DataQualityError(ValueError):
    pass


class DuplicateFileError(RuntimeError):
    pass


def normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()
    return text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_identifier(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return re.sub(r"\.0$", "", text)


def _clean_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _scalar(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.date()
    return value


def _row_hash(row: pd.Series) -> str:
    values = {column: _scalar(row[column]) for column in row.index if column != "fila_origen"}
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_and_prepare(path: Path, source: MarketSource) -> PreparedMarketData:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(
            path,
            sheet_name=source.sheet_name or 0,
            header=source.header_row - 1,
        )
    elif suffix == ".csv":
        frame = pd.read_csv(path, header=source.header_row - 1)
    else:
        raise ValueError(f"Formato no soportado: {suffix}. Use .xlsx, .xlsm o .csv")

    frame.columns = [normalize_header(column) for column in frame.columns]
    missing = sorted(set(EXPECTED_COLUMNS) - set(frame.columns))
    extras = sorted(set(frame.columns) - set(EXPECTED_COLUMNS))
    if missing:
        raise DataQualityError(f"Faltan columnas obligatorias: {missing}")
    if extras:
        raise DataQualityError(f"Hay columnas inesperadas: {extras}")

    frame = frame[EXPECTED_COLUMNS].rename(columns=RENAME_COLUMNS).copy()
    frame["fila_origen"] = range(source.header_row + 1, source.header_row + 1 + len(frame))

    frame["codigo_unidad"] = frame["codigo_unidad"].map(_clean_identifier)
    frame["numero_inmueble"] = frame["numero_inmueble"].map(_clean_identifier)
    for column in [c for c in TEXT_COLUMNS if c not in {"codigo_unidad", "numero_inmueble"}]:
        frame[column] = frame[column].map(_clean_text)

    frame["moneda"] = frame["moneda"].str.upper()
    frame["estado_comercial"] = frame["estado_comercial"].str.upper()
    frame["estado_comercial_original"] = frame["estado_comercial_original"].str.upper()

    errors: list[str] = []
    for column in NUMERIC_COLUMNS:
        original_non_null = frame[column].notna()
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        invalid = original_non_null & frame[column].isna()
        if invalid.any():
            errors.append(f"{column}: {int(invalid.sum())} valores no numéricos")

    for column in INTEGER_COLUMNS:
        original_non_null = frame[column].notna()
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid = original_non_null & (numeric.isna() | (numeric % 1 != 0))
        if invalid.any():
            errors.append(f"{column}: {int(invalid.sum())} valores no enteros")
        frame[column] = numeric.astype("Int64")

    for column in DATE_COLUMNS:
        original_non_null = frame[column].notna()
        parsed = pd.to_datetime(frame[column], errors="coerce")
        invalid = original_non_null & parsed.isna()
        if invalid.any():
            errors.append(f"{column}: {int(invalid.sum())} fechas inválidas")
        frame[column] = parsed.dt.date

    if frame["codigo_unidad"].isna().any():
        errors.append(f"codigo_unidad: {int(frame['codigo_unidad'].isna().sum())} valores nulos")
    duplicate_codes = frame.loc[frame["codigo_unidad"].duplicated(keep=False), "codigo_unidad"].dropna().unique()
    if len(duplicate_codes):
        errors.append(f"codigo_unidad: {len(duplicate_codes)} códigos duplicados en el archivo")
    for column in ["area_techada_m2", "area_libre_m2", "area_venta_m2", "precio_lista", "precio_venta", "precio_m2"]:
        negatives = frame[column].fillna(0).lt(0)
        if negatives.any():
            errors.append(f"{column}: {int(negatives.sum())} valores negativos")
    if errors:
        raise DataQualityError("; ".join(errors))

    warnings: list[str] = []
    if frame["referido"].isna().all():
        warnings.append("La columna referido está completamente vacía.")

    comparable = frame["precio_venta"].notna() & frame["area_venta_m2"].gt(0) & frame["precio_m2"].notna()
    calculated = frame.loc[comparable, "precio_venta"] / frame.loc[comparable, "area_venta_m2"]
    differences = (calculated - frame.loc[comparable, "precio_m2"]).abs().gt(0.05)
    if differences.any():
        warnings.append(
            f"{int(differences.sum())} filas tienen precio_m2 distinto de precio_venta/area_venta_m2 por más de 0.05."
        )

    frame["hash_fila"] = frame.apply(_row_hash, axis=1)
    return PreparedMarketData(frame=frame, warnings=warnings, file_hash=_file_sha256(path))


HISTORY_COLUMNS = [
    "carga_id", "snapshot_id", "source_id", "empresa_fuente", "codigo_proyecto",
    "nombre_proyecto", "fecha_snapshot", "codigo_unidad", "torre", "tipo_unidad",
    "tipologia", "numero_inmueble", "piso", "vista", "area_techada_m2",
    "area_libre_m2", "area_venta_m2", "dormitorios", "moneda", "precio_lista",
    "precio_venta", "precio_m2", "fecha_separacion", "fecha_venta",
    "estado_comercial", "estado_comercial_original", "referido", "archivo_origen",
    "hoja_origen", "fila_origen", "hash_fila",
]


def _records(
    prepared: PreparedMarketData,
    source: MarketSource,
    path: Path,
    snapshot_date: date,
    carga_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> list[dict[str, Any]]:
    common = {
        "carga_id": carga_id,
        "snapshot_id": snapshot_id,
        "source_id": source.source_id,
        "empresa_fuente": source.empresa_fuente,
        "codigo_proyecto": source.codigo_proyecto,
        "nombre_proyecto": source.nombre_proyecto,
        "fecha_snapshot": snapshot_date,
        "archivo_origen": path.name,
        "hoja_origen": source.sheet_name,
    }
    return [
        {**common, **{column: _scalar(row[column]) for column in prepared.frame.columns}}
        for _, row in prepared.frame.iterrows()
    ]


def load_snapshot(
    conn: Connection,
    path: Path,
    source: MarketSource,
    snapshot_date: date,
) -> dict[str, Any]:
    prepared = read_and_prepare(path, source)
    carga_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    records = _records(prepared, source, path, snapshot_date, carga_id, snapshot_id)

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT carga_id FROM raw_mercado.cargas WHERE source_id=%s AND hash_archivo=%s",
            (source.source_id, prepared.file_hash),
        )
        existing = cursor.fetchone()
    if existing:
        conn.rollback()
        raise DuplicateFileError(
            f"El archivo ya fue procesado para {source.source_id}; carga_id={existing[0]}"
        )

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO raw_mercado.cargas (
                    carga_id, snapshot_id, source_id, empresa_fuente, codigo_proyecto,
                    nombre_proyecto, fecha_snapshot, archivo_origen, hoja_origen,
                    hash_archivo, estado, filas_leidas, advertencias
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'STARTED',%s,%s::jsonb)
                """,
                (
                    carga_id, snapshot_id, source.source_id, source.empresa_fuente,
                    source.codigo_proyecto, source.nombre_proyecto, snapshot_date,
                    path.name, source.sheet_name, prepared.file_hash, len(records),
                    json.dumps(prepared.warnings, ensure_ascii=False),
                ),
            )
        conn.commit()

        placeholders = ",".join(["%s"] * len(HISTORY_COLUMNS))
        history_sql = (
            f"INSERT INTO raw_mercado.unidades_historial ({','.join(HISTORY_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        current_columns = [c for c in HISTORY_COLUMNS if c != "snapshot_id"]
        current_columns.insert(1, "snapshot_id")
        update_columns = [
            c for c in current_columns
            if c not in {"source_id", "codigo_unidad"}
        ]
        current_sql = f"""
            INSERT INTO raw_mercado.unidades ({','.join(current_columns)})
            VALUES ({','.join(['%s'] * len(current_columns))})
            ON CONFLICT (source_id, codigo_unidad) DO UPDATE SET
                {','.join(f'{c}=EXCLUDED.{c}' for c in update_columns)},
                cargado_en=now()
            WHERE EXCLUDED.fecha_snapshot >= raw_mercado.unidades.fecha_snapshot
        """

        with conn.cursor() as cursor:
            history_values = [tuple(record[column] for column in HISTORY_COLUMNS) for record in records]
            cursor.executemany(history_sql, history_values)
            current_values = [tuple(record[column] for column in current_columns) for record in records]
            cursor.executemany(current_sql, current_values)
            cursor.execute(
                """
                UPDATE raw_mercado.cargas
                SET estado='SUCCESS', filas_insertadas_historial=%s,
                    filas_actualizadas_actual=%s, finalizado_en=now()
                WHERE carga_id=%s
                """,
                (len(records), len(records), carga_id),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE raw_mercado.cargas
                SET estado='FAILED', error=%s, finalizado_en=now()
                WHERE carga_id=%s
                """,
                (str(exc), carga_id),
            )
        conn.commit()
        raise

    return {
        "carga_id": str(carga_id),
        "snapshot_id": str(snapshot_id),
        "fecha_snapshot": snapshot_date.isoformat(),
        "filas": len(records),
        "advertencias": prepared.warnings,
        "hash_archivo": prepared.file_hash,
    }


def default_snapshot_date(timezone_name: str) -> date:
    return datetime.now(ZoneInfo(timezone_name)).date()
