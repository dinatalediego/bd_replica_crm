from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main() -> int:
    settings = load_settings()

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("CALL pricing.refresh_fact_proyeccion_pricing()")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pricing.v_projection_health")
            row = cur.fetchone()
            columns = [d.name for d in cur.description]

    health = dict(zip(columns, row))
    print("Pricing Projection Mart refrescado:")
    for key, value in health.items():
        print(f"  {key}: {value}")

    hard_fail = {
        "filas_vs_esperadas": (
            int(health["filas_fact"] or 0) != int(health["filas_esperadas"] or 0)
        ),
        "errores_cobertura_escenario": int(health["errores_cobertura_escenario"] or 0) != 0,
        "granos_duplicados": int(health["granos_duplicados"] or 0) != 0,
        "filas_invalidas": int(health["filas_invalidas"] or 0) != 0,
    }
    failures = [name for name, failed in hard_fail.items() if failed]
    if failures:
        print("Gate Pricing Projection NO aprobado: " + ", ".join(failures))
        return 1

    print("Gate Pricing Projection APROBADO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
