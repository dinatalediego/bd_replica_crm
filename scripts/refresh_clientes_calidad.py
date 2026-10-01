from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main() -> int:
    settings = load_settings()

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
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
