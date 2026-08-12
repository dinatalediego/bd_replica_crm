from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import ConfigurationError
from .identifiers import validate_identifier

Strategy = Literal["incremental", "full_refresh", "append"]


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str | None = None
    ssl: bool = True
    connect_timeout: int = 20
    statement_timeout_ms: int = 900_000
    tcp_keepalive: bool = True
    tcp_keepalive_idle: int = 30
    tcp_keepalive_interval: int = 15
    tcp_keepalive_count: int = 5


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    redshift: DatabaseSettings
    postgres: DatabaseSettings
    log_level: str = "INFO"
    default_batch_size: int = 5000
    default_lookback_hours: int = 48
    lock_timeout_seconds: int = 5


@dataclass(frozen=True)
class SourceColumn:
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool
    character_maximum_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None


@dataclass
class TableConfig:
    source_schema: str
    source_table: str
    target_schema: str = "raw_cygnus"
    target_table: str | None = None
    strategy: Strategy = "incremental"
    key_columns: list[str] = field(default_factory=list)
    watermark_column: str | None = None
    batch_size: int = 5000
    lookback_hours: int = 48
    enabled: bool = False
    create_target_if_missing: bool = True
    add_etl_columns: bool = True
    initial_where: str | None = None
    column_type_overrides: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.target_table = self.target_table or self.source_table
        validate_identifier(self.source_schema, "source_schema")
        validate_identifier(self.source_table, "source_table")
        validate_identifier(self.target_schema, "target_schema")
        validate_identifier(self.target_table, "target_table")
        for col in self.key_columns:
            validate_identifier(col, "key_columns")
        if self.watermark_column:
            validate_identifier(self.watermark_column, "watermark_column")
        if self.strategy not in {"incremental", "full_refresh", "append"}:
            raise ConfigurationError(f"Estrategia no soportada: {self.strategy}")
        if self.strategy == "incremental" and not self.key_columns:
            raise ConfigurationError(
                f"{self.source_schema}.{self.source_table}: incremental requiere key_columns."
            )
        if self.strategy == "incremental" and not self.watermark_column:
            raise ConfigurationError(
                f"{self.source_schema}.{self.source_table}: incremental requiere watermark_column."
            )
        if self.strategy == "append" and not self.watermark_column:
            raise ConfigurationError(
                f"{self.source_schema}.{self.source_table}: append requiere watermark_column."
            )
        if self.batch_size <= 0:
            raise ConfigurationError("batch_size debe ser mayor a cero.")
        if self.lookback_hours < 0:
            raise ConfigurationError("lookback_hours no puede ser negativo.")
        if self.initial_where and ";" in self.initial_where:
            raise ConfigurationError("initial_where no puede contener punto y coma.")
        for column_name, pg_type in self.column_type_overrides.items():
            validate_identifier(column_name, "column_type_overrides")
            if not pg_type or any(token in pg_type for token in (";", "--", "/*", "*/")):
                raise ConfigurationError(
                    f"Tipo PostgreSQL inseguro para {column_name}: {pg_type!r}"
                )

    @property
    def source_name(self) -> str:
        return f"{self.source_schema}.{self.source_table}"

    @property
    def target_name(self) -> str:
        return f"{self.target_schema}.{self.target_table}"


@dataclass(frozen=True)
class SyncState:
    last_watermark: str | None
    watermark_data_type: str | None
    rows_last_run: int = 0


@dataclass
class SyncResult:
    source_name: str
    target_name: str
    strategy: str
    rows_extracted: int
    rows_loaded: int
    watermark_before: str | None
    watermark_after: str | None
    status: str
    run_id: str
    message: str = ""


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update({k: v for k, v in override.items() if v is not None})
    return merged
