from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"
    connect_timeout: int = 10

    @classmethod
    def from_env(cls) -> "PostgresSettings":
        required = {
            "POSTGRES_HOST": os.getenv("POSTGRES_HOST"),
            "POSTGRES_DATABASE": os.getenv("POSTGRES_DATABASE"),
            "POSTGRES_USER": os.getenv("POSTGRES_USER"),
            "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing PostgreSQL settings: " + ", ".join(sorted(missing))
            )

        return cls(
            host=required["POSTGRES_HOST"] or "",
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=required["POSTGRES_DATABASE"] or "",
            user=required["POSTGRES_USER"] or "",
            password=required["POSTGRES_PASSWORD"] or "",
            sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
            connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
        )

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode,
            connect_timeout=self.connect_timeout,
            autocommit=False,
        )
