from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import make_dsn

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT / "sql" / "40_unidades_multifuente" / "01_v_unidades_fuentes.sql"


def _database_dsn() -> str:
    load_dotenv(ROOT / ".env", override=False)
    direct = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if direct and not (len(direct) > 2 and direct[1:3] in {":\\", ":/"}):
        return direct.strip()

    required = {
        "host": os.getenv("POSTGRES_HOST"),
        "dbname": os.getenv("POSTGRES_DATABASE"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Faltan variables PostgreSQL en .env: {', '.join(missing)}")

    return make_dsn(
        host=required["host"],
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=required["dbname"],
        user=required["user"],
        password=required["password"],
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
        connect_timeout=os.getenv("POSTGRES_CONNECT_TIMEOUT", "10"),
    )


def main() -> int:
    sql_text = SQL_FILE.read_text(encoding="utf-8")
    conn = psycopg2.connect(_database_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(sql_text)
            cur.execute(
                """
                SELECT esquema_fuente, count(*)
                FROM core.v_unidades_fuentes
                GROUP BY esquema_fuente
                ORDER BY esquema_fuente
                """
            )
            counts = cur.fetchall()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[OK] core.v_unidades_fuentes creada/actualizada")
    for fuente, filas in counts:
        print(f"  {fuente}: {filas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
