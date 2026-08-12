from __future__ import annotations

import logging

import psycopg
import redshift_connector

from .models import AppSettings

LOGGER = logging.getLogger(__name__)


def connect_redshift(settings: AppSettings):
    cfg = settings.redshift
    LOGGER.debug("Conectando a Redshift %s:%s/%s", cfg.host, cfg.port, cfg.database)
    connection = redshift_connector.connect(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.user,
        password=cfg.password,
        ssl=cfg.ssl,
        sslmode=cfg.sslmode,
        timeout=cfg.connect_timeout,
        tcp_keepalive=cfg.tcp_keepalive,
        tcp_keepalive_idle=cfg.tcp_keepalive_idle,
        tcp_keepalive_interval=cfg.tcp_keepalive_interval,
        tcp_keepalive_count=cfg.tcp_keepalive_count,
        application_name="replica_redshift_local",
    )
    connection.autocommit = True
    if cfg.statement_timeout_ms > 0:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET statement_timeout TO {int(cfg.statement_timeout_ms)}")
        except Exception:
            LOGGER.warning(
                "No se pudo configurar statement_timeout en Redshift; se continuará con el valor de la sesión.",
                exc_info=True,
            )
    return connection


def connect_postgres(settings: AppSettings) -> psycopg.Connection:
    cfg = settings.postgres
    LOGGER.debug("Conectando a PostgreSQL %s:%s/%s", cfg.host, cfg.port, cfg.database)
    return psycopg.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.database,
        user=cfg.user,
        password=cfg.password,
        sslmode=cfg.sslmode or "prefer",
        connect_timeout=cfg.connect_timeout,
        application_name="replica_redshift_local",
        autocommit=False,
    )
