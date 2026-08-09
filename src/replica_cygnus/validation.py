from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import get_source_columns
from .identifiers import qualified_redshift, quote_redshift_identifier
from .models import TableConfig
from .target_schema import validate_config_columns


@dataclass
class ValidationReport:
    source_name: str
    ok: bool = True
    messages: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.ok = False
        self.messages.append(f"ERROR: {message}")

    def add_warning(self, message: str) -> None:
        self.messages.append(f"ADVERTENCIA: {message}")

    def add_ok(self, message: str) -> None:
        self.messages.append(f"OK: {message}")


def validate_source_config(source_conn, cfg: TableConfig, deep: bool = False) -> ValidationReport:
    report = ValidationReport(source_name=cfg.source_name)
    columns = get_source_columns(source_conn, cfg.source_schema, cfg.source_table)
    if not columns:
        report.add_error("La tabla no existe o el usuario no puede ver sus columnas.")
        return report

    try:
        validate_config_columns(cfg, columns)
        report.add_ok(f"Se encontraron {len(columns)} columnas y la configuración usa nombres válidos.")
    except Exception as exc:
        report.add_error(str(exc))
        return report

    if cfg.strategy == "incremental":
        null_condition = " OR ".join(
            f"{quote_redshift_identifier(name)} IS NULL" for name in cfg.key_columns
        )
        with source_conn.cursor() as cursor:
            cursor.execute(
                f"SELECT 1 FROM {qualified_redshift(cfg.source_schema, cfg.source_table)} "
                f"WHERE {null_condition} LIMIT 1"
            )
            if cursor.fetchone():
                report.add_error("Existen filas con llave nula; el UPSERT no sería seguro.")
            else:
                report.add_ok("No se detectaron llaves nulas.")

        if deep:
            key_sql = ", ".join(quote_redshift_identifier(name) for name in cfg.key_columns)
            with source_conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {key_sql}, COUNT(*) AS n "
                    f"FROM {qualified_redshift(cfg.source_schema, cfg.source_table)} "
                    f"GROUP BY {key_sql} HAVING COUNT(*) > 1 LIMIT 5"
                )
                duplicates = cursor.fetchall()
            if duplicates:
                report.add_warning(
                    "La fuente contiene llaves repetidas. El sistema conservará la fila con "
                    "watermark más reciente dentro de cada lote, pero debes confirmar la llave."
                )
            else:
                report.add_ok("No se detectaron llaves duplicadas en la validación profunda.")

    if cfg.watermark_column:
        with source_conn.cursor() as cursor:
            cursor.execute(
                f"SELECT MIN({quote_redshift_identifier(cfg.watermark_column)}), "
                f"MAX({quote_redshift_identifier(cfg.watermark_column)}) "
                f"FROM {qualified_redshift(cfg.source_schema, cfg.source_table)}"
            )
            min_value, max_value = cursor.fetchone()
        if max_value is None:
            report.add_error("La columna watermark no contiene valores utilizables.")
        else:
            report.add_ok(f"Rango watermark: {min_value} -> {max_value}")

    return report
