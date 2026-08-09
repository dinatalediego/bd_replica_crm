from __future__ import annotations

from .models import SourceColumn


def postgres_type(column: SourceColumn, override: str | None = None) -> str:
    if override:
        return override

    data_type = column.data_type.lower().strip()

    if data_type in {"bigint", "int8"}:
        return "bigint"
    if data_type in {"integer", "int", "int4"}:
        return "integer"
    if data_type in {"smallint", "int2"}:
        return "smallint"
    if data_type in {"real", "float4"}:
        return "real"
    if data_type in {"double precision", "float8", "float"}:
        return "double precision"
    if data_type in {"boolean", "bool"}:
        return "boolean"
    if data_type == "date":
        return "date"
    if data_type in {"timestamp without time zone", "timestamp"}:
        return "timestamp without time zone"
    if data_type in {"timestamp with time zone", "timestamptz"}:
        return "timestamp with time zone"
    if data_type.startswith("time"):
        return "time"
    if data_type in {"numeric", "decimal"}:
        if column.numeric_precision is not None and column.numeric_scale is not None:
            return f"numeric({column.numeric_precision},{column.numeric_scale})"
        if column.numeric_precision is not None:
            return f"numeric({column.numeric_precision})"
        return "numeric"
    if data_type in {"character varying", "varchar", "nvarchar"}:
        if column.character_maximum_length and column.character_maximum_length > 0:
            return f"varchar({column.character_maximum_length})"
        return "text"
    if data_type in {"character", "char", "nchar", "bpchar"}:
        if column.character_maximum_length and column.character_maximum_length > 0:
            return f"char({column.character_maximum_length})"
        return "text"
    if data_type in {"varbyte", "bytea"}:
        return "bytea"

    # SUPER, GEOMETRY, GEOGRAPHY, HLLSKETCH y tipos no reconocidos se guardan como texto
    # para priorizar una réplica robusta. Pueden ajustarse con column_type_overrides.
    return "text"


def is_datetime_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    value = data_type.lower()
    return "timestamp" in value or value == "date"


def is_numeric_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    value = data_type.lower()
    return any(token in value for token in ("int", "numeric", "decimal", "float", "double", "real"))
