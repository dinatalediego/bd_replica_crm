from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from .errors import SyncError
from .identifiers import qualified_redshift, quote_redshift_identifier
from .models import SourceColumn, SyncState, TableConfig
from .type_mapping import is_datetime_type

def serialize_watermark(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def deserialize_watermark(value: str | None, data_type: str | None) -> object | None:
    if value is None:
        return None
    kind = (data_type or "").lower()
    if "timestamp" in kind:
        return datetime.fromisoformat(value)
    if kind == "date":
        return date.fromisoformat(value)
    if any(token in kind for token in ("numeric", "decimal")):
        return Decimal(value)
    if any(token in kind for token in ("bigint", "integer", "smallint", "int")):
        return int(value)
    if any(token in kind for token in ("double", "float", "real")):
        return float(value)
    return value


def apply_lookback(value: object, data_type: str, hours: int) -> object:
    if hours <= 0 or not is_datetime_type(data_type):
        return value
    if isinstance(value, datetime):
        return value - timedelta(hours=hours)
    if isinstance(value, date):
        days = max(1, math.ceil(hours / 24))
        return value - timedelta(days=days)
    return value


def build_source_query(
    cfg: TableConfig,
    columns: list[SourceColumn],
    state: SyncState,
    max_rows: int | None = None,
) -> tuple[str, tuple[object, ...]]:
    column_sql = ", ".join(quote_redshift_identifier(column.name) for column in columns)
    query = f"SELECT {column_sql} FROM {qualified_redshift(cfg.source_schema, cfg.source_table)}"
    conditions: list[str] = []
    params: list[object] = []

    watermark_type = next(
        (column.data_type for column in columns if column.name == cfg.watermark_column),
        None,
    )
    if cfg.strategy in {"incremental", "append"} and state.last_watermark is not None:
        threshold = deserialize_watermark(state.last_watermark, watermark_type or state.watermark_data_type)
        if cfg.strategy == "incremental" and threshold is not None and watermark_type:
            threshold = apply_lookback(threshold, watermark_type, cfg.lookback_hours)
            operator = ">="
        else:
            operator = ">"
        conditions.append(f"{quote_redshift_identifier(cfg.watermark_column or '')} {operator} %s")
        params.append(threshold)
    elif cfg.initial_where:
        conditions.append(f"({cfg.initial_where})")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    order_columns: list[str] = []
    if cfg.watermark_column:
        order_columns.append(quote_redshift_identifier(cfg.watermark_column))
    order_columns.extend(quote_redshift_identifier(name) for name in cfg.key_columns)
    if order_columns:
        query += " ORDER BY " + ", ".join(dict.fromkeys(order_columns))

    if max_rows is not None:
        if max_rows <= 0:
            raise SyncError("max_rows debe ser mayor a cero.")
        query += f" LIMIT {int(max_rows)}"
    return query, tuple(params)

