from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigurationError
from .models import AppSettings, DatabaseSettings


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Falta la variable de entorno {name} en .env")
    return value.strip()


def load_settings(project_root: Path | None = None) -> AppSettings:
    root = project_root or Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")

    redshift = DatabaseSettings(
        host=_required("REDSHIFT_HOST"),
        port=int(os.getenv("REDSHIFT_PORT", "5439")),
        database=_required("REDSHIFT_DATABASE"),
        user=_required("REDSHIFT_USER"),
        password=_required("REDSHIFT_PASSWORD"),
        sslmode=os.getenv("REDSHIFT_SSLMODE", "verify-ca"),
        ssl=_as_bool(os.getenv("REDSHIFT_SSL"), True),
        # redshift_connector usa `timeout` también durante lecturas del socket.
        # Mantenerlo en 20 s puede cortar consultas válidas bajo carga/WLM.
        connect_timeout=int(os.getenv("REDSHIFT_SOCKET_TIMEOUT", "300")),
        statement_timeout_ms=int(os.getenv("REDSHIFT_STATEMENT_TIMEOUT_MS", "900000")),
        tcp_keepalive=_as_bool(os.getenv("REDSHIFT_TCP_KEEPALIVE"), True),
        tcp_keepalive_idle=int(os.getenv("REDSHIFT_TCP_KEEPALIVE_IDLE", "30")),
        tcp_keepalive_interval=int(os.getenv("REDSHIFT_TCP_KEEPALIVE_INTERVAL", "15")),
        tcp_keepalive_count=int(os.getenv("REDSHIFT_TCP_KEEPALIVE_COUNT", "5")),
    )
    postgres = DatabaseSettings(
        host=_required("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=_required("POSTGRES_DATABASE"),
        user=_required("POSTGRES_USER"),
        password=_required("POSTGRES_PASSWORD"),
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
        ssl=True,
        connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
        statement_timeout_ms=0,
    )
    return AppSettings(
        project_root=root,
        redshift=redshift,
        postgres=postgres,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        default_batch_size=int(os.getenv("DEFAULT_BATCH_SIZE", "5000")),
        default_lookback_hours=int(os.getenv("DEFAULT_LOOKBACK_HOURS", "48")),
        lock_timeout_seconds=int(os.getenv("LOCK_TIMEOUT_SECONDS", "5")),
    )
