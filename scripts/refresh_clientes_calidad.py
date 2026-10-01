from __future__ import annotations

import argparse

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def needs_refresh(raw_count, staging_count, raw_loaded_at, staging_refreshed_at) -> bool:
    if raw_count != staging_count:
        return True
    if raw_count == 0:
        return False
    if raw_loaded_at is None or staging_refreshed_at is None:
        return True
    return raw_loaded_at > staging_refreshed_at


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh de calidad de clientes local.")
    parser.add_argument("--if-needed", action="store_true", help="Omite el refresh si RAW no cambió.")
    args = parser.parse_args()
    settings = load_settings()

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout TO '15s'")
            cur.execute("SELECT COUNT(*), MAX(_etl_loaded_at) FROM raw_cygnus.clientes")
            filas_raw_inicio, raw_loaded_at = cur.fetchone()
            filas_raw_inicio = int(filas_raw_inicio)
            if args.if_needed:
                cur.execute("SELECT COUNT(*), MIN(refreshed_at) FROM staging.clientes_calidad")
                staging_count, staging_refreshed_at = cur.fetchone()
                if not needs_refresh(filas_raw_inicio, staging_count, raw_loaded_at, staging_refreshed_at):
                    print("SKIP clientes_calidad: RAW sin cambios", flush=True)
                    return 0
            print(
                f"Preparando staging.clientes_calidad desde {filas_raw_inicio:,} filas RAW...",
                flush=True,
            )

            cur.execute("CALL staging.refresh_clientes_calidad()")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM staging.v_clientes_calidad_health")
            row = cur.fetchone()
            columns = [d.name for d in cur.description]

    health = dict(zip(columns, row))
    print("staging.clientes_calidad refrescado:")
    for key, value in health.items():
        print(f"  {key}: {value}")

    filas_raw = int(health["filas_raw"] or 0)
    filas_staging = int(health["filas_staging"] or 0)
    if filas_raw != filas_staging:
        print(
            "Gate clientes_calidad NO aprobado: "
            f"filas_raw={filas_raw} filas_staging={filas_staging}"
        )
        return 1

    print("Gate clientes_calidad APROBADO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
