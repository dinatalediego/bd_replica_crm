"""Print aggregate marketing audience health without exposing customer PII."""

from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _row_dict(cur):
    row = cur.fetchone()
    return dict(zip([column.name for column in cur.description], row)) if row else None


def main() -> int:
    with connect_postgres(load_settings(require_source=False)) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('analytics.marketing_audiencias')")
            if cur.fetchone()[0] is None:
                raise RuntimeError(
                    "No existe analytics.marketing_audiencias; ejecutar schema_sync primero."
                )
            cur.execute("SELECT * FROM analytics.v_marketing_audiencias_health")
            health = _row_dict(cur)
            cur.execute(
                """
                SELECT etapa_maxima, count(*)::bigint AS personas
                FROM analytics.marketing_audiencias
                GROUP BY etapa_maxima
                ORDER BY etapa_maxima
                """
            )
            stages = cur.fetchall()
            cur.execute(
                """
                SELECT run_id, finished_at, inactivity_days, personas, positivas,
                       negativas_sin_avance, exclusiones, aptas_entrega_externa
                FROM analytics.marketing_audiencias_refresh_runs
                ORDER BY run_id DESC
                LIMIT 1
                """
            )
            latest = _row_dict(cur)

    print("[MARKETING_AUDIENCES_HEALTH]")
    for key, value in (health or {}).items():
        print(f"  {key}: {value}")
    print("[ETAPA_MAXIMA]")
    for stage, count in stages:
        print(f"  {stage}: {count}")
    print("[ULTIMO_REFRESH]")
    for key, value in (latest or {}).items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
