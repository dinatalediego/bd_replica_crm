from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import make_dsn

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.raw_mercado_loader import load_raw_mercado


def _looks_like_windows_path(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.match(r"^[A-Za-z]:[\\/]", value.strip()))


def _build_database_dsn(explicit: str | None = None) -> str | None:
    # Reutiliza la configuración PostgreSQL existente del proyecto.
    load_dotenv(ROOT / ".env", override=False)

    if explicit and not _looks_like_windows_path(explicit):
        return explicit.strip()

    env_dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if env_dsn and not _looks_like_windows_path(env_dsn):
        return env_dsn.strip()

    required = {
        "host": os.getenv("POSTGRES_HOST"),
        "dbname": os.getenv("POSTGRES_DATABASE"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    missing = [name for name, value in required.items() if value is None or not value.strip()]
    if missing:
        return None

    return make_dsn(
        host=required["host"].strip(),
        port=(os.getenv("POSTGRES_PORT") or "5432").strip(),
        dbname=required["dbname"].strip(),
        user=required["user"].strip(),
        password=required["password"],
        sslmode=(os.getenv("POSTGRES_SSLMODE") or "prefer").strip(),
        connect_timeout=(os.getenv("POSTGRES_CONNECT_TIMEOUT") or "10").strip(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga controlada CSV -> PostgreSQL raw_mercado.unidades")
    parser.add_argument("file", help="Ruta del CSV de mercado")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--schema", default="raw_mercado")
    parser.add_argument("--table", default="unidades")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--append", action="store_true", help="No hace TRUNCATE antes de insertar")
    args = parser.parse_args()

    database_dsn = _build_database_dsn(args.database_url)
    if not database_dsn:
        parser.error(
            "No se pudo resolver PostgreSQL. Define DATABASE_URL/POSTGRES_URL o las variables "
            "POSTGRES_HOST, POSTGRES_DATABASE, POSTGRES_USER y POSTGRES_PASSWORD en .env."
        )

    try:
        psycopg2.extensions.parse_dsn(database_dsn)
    except psycopg2.ProgrammingError as exc:
        parser.error(f"La configuración PostgreSQL no es un DSN válido: {exc}")

    result = load_raw_mercado(
        database_dsn,
        args.file,
        schema_name=args.schema,
        table_name=args.table,
        delimiter=args.delimiter,
        encoding=args.encoding,
        snapshot=not args.no_snapshot,
        replace=not args.append,
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
