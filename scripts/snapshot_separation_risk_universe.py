from __future__ import annotations

from psycopg.rows import dict_row

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main() -> int:
    settings = load_settings()
    with connect_postgres(settings) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select decision_intelligence.snapshot_separation_fall_risk_universe() as affected"
            )
            affected = int(cur.fetchone()["affected"])
            cur.execute(
                """
                select *
                from decision_intelligence.v_candidate_universe_snapshot_health
                where decision_key = 'separation_fall_risk'
                order by snapshot_at desc
                limit 1
                """
            )
            health = dict(cur.fetchone() or {})
        conn.commit()

    print("Candidate universe snapshot completado")
    print(f"  affected: {affected}")
    for key, value in health.items():
        print(f"  {key}: {value}")

    duplicate_entities = int(health.get("duplicate_entities") or 0)
    if duplicate_entities:
        print("Gate snapshot NO aprobado: hay entity_id duplicados en el snapshot.")
        return 1

    print("Gate snapshot APROBADO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
