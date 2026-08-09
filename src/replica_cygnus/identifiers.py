from __future__ import annotations

import re

from .errors import ConfigurationError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    """Valida identificadores SQL configurables para reducir riesgo de inyección."""
    if not value or not _IDENTIFIER_RE.fullmatch(value):
        raise ConfigurationError(
            f"{field_name} inválido: {value!r}. "
            "Use letras, números, guion bajo o $; no use espacios ni SQL."
        )
    return value


def quote_redshift_identifier(value: str) -> str:
    """Cita un identificador proveniente del catálogo de Redshift."""
    if value is None or value == "":
        raise ConfigurationError("El identificador SQL no puede estar vacío.")
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def qualified_redshift(schema: str, table: str) -> str:
    validate_identifier(schema, "source_schema")
    validate_identifier(table, "source_table")
    return f"{quote_redshift_identifier(schema)}.{quote_redshift_identifier(table)}"
