from __future__ import annotations

import argparse

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def refresh(conn, *, full: bool = False, timeout_seconds: int = 900) -> int:
    """Validate in the same transaction; a failed gate must never be committed."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('lock_timeout', '30s', true)")
            cur.execute("SELECT set_config('statement_timeout', %s, true)",
                        (f"{timeout_seconds}s",))
            cur.execute("SELECT set_config('medallio.clientes_calidad_full', %s, true)",
                        ('on' if full else 'off',))
            cur.execute("CALL staging.refresh_clientes_calidad()")
            cur.execute("SELECT * FROM staging.v_clientes_calidad_health")
            row = cur.fetchone()
            columns = [d.name for d in cur.description]
            health = dict(zip(columns, row))
            filas_raw = int(health["filas_raw"] or 0)
            filas_staging = int(health["filas_staging"] or 0)
            if filas_raw != filas_staging:
                raise RuntimeError(
                    "Gate clientes_calidad NO aprobado: "
                    f"filas_raw={filas_raw} filas_staging={filas_staging}"
                )
            cur.execute("SELECT mode, source_rows, inserted_rows, updated_rows, "
                        "deleted_rows, unchanged_rows, finished_at - started_at AS duration "
                        "FROM staging.clientes_calidad_refresh_runs ORDER BY run_id DESC LIMIT 1")
            run = dict(zip([d.name for d in cur.description], cur.fetchone()))

    print("staging.clientes_calidad refrescado:")
    for key, value in health.items():
        print(f"  {key}: {value}")
    print("[CLIENTES_CALIDAD] " + " | ".join(f"{k}={v}" for k, v in run.items()))
    print("Gate clientes_calidad APROBADO.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh DQ incremental sobre PostgreSQL local.")
    parser.add_argument("--full", action="store_true", help="Recalcula todas las reglas una vez.")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds debe ser positivo")
    settings = load_settings(require_source=False)
    with connect_postgres(settings) as conn:
        return refresh(conn, full=args.full, timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
