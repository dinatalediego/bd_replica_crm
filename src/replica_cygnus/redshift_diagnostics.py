from __future__ import annotations

import sys
import time

from .connections import connect_redshift
from .identifiers import qualified_redshift, validate_identifier
from .settings import load_settings


def _timed(label: str, fn):
    start = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        elapsed = time.perf_counter() - start
        print(f"FAIL | {label} | {elapsed:.2f}s | {type(exc).__name__}: {exc}")
        raise
    elapsed = time.perf_counter() - start
    print(f"OK   | {label} | {elapsed:.2f}s")
    return result


def main() -> int:
    schema = sys.argv[1] if len(sys.argv) > 1 else "grupocygnus"
    table = sys.argv[2] if len(sys.argv) > 2 else "proforma_unidad"
    validate_identifier(schema, "schema")
    validate_identifier(table, "table")

    settings = load_settings()
    print("Diagnóstico Redshift")
    print(f"Destino: {settings.redshift.host}:{settings.redshift.port}/{settings.redshift.database}")
    print(f"Tabla:   {schema}.{table}")
    print(f"Socket timeout: {settings.redshift.connect_timeout}s")
    print(
        "Keepalive: "
        f"{settings.redshift.tcp_keepalive} "
        f"idle={settings.redshift.tcp_keepalive_idle}s "
        f"interval={settings.redshift.tcp_keepalive_interval}s "
        f"count={settings.redshift.tcp_keepalive_count}"
    )

    conn = _timed("conectar", lambda: connect_redshift(settings))
    try:
        def ping():
            with conn.cursor() as cur:
                cur.execute("SELECT current_database, current_user, current_timestamp")
                row = cur.fetchone()
                print(f"     database={row[0]} user={row[1]} server_time={row[2]}")
        _timed("SELECT identidad", ping)

        def show_columns():
            with conn.cursor() as cur:
                cur.execute(f"SHOW COLUMNS FROM TABLE {qualified_redshift(schema, table)}")
                rows = cur.fetchall()
                print(f"     columnas={len(rows)}")
                if rows:
                    names = [str(col[0]).lower() for col in (cur.description or [])]
                    try:
                        i_name = names.index("column_name")
                        i_type = names.index("data_type")
                        for row in rows[:10]:
                            print(f"     - {row[i_name]} :: {row[i_type]}")
                    except ValueError:
                        pass
        _timed("SHOW COLUMNS", show_columns)

        def sample():
            with conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM {qualified_redshift(schema, table)} LIMIT 1")
                cur.fetchone()
        _timed("SELECT 1 FROM tabla LIMIT 1", sample)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
