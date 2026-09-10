from __future__ import annotations

import argparse

from psycopg import sql

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


DEFAULT_SCHEMAS = ("core", "analytics", "analytics_compare", "gold")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresca materialized views de capas de serving para Power BI."
    )
    parser.add_argument(
        "--schema",
        action="append",
        dest="schemas",
        default=[],
        help="Schema a incluir; puede repetirse.",
    )
    args = parser.parse_args()
    schemas = tuple(args.schemas) or DEFAULT_SCHEMAS

    settings = load_settings()
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT schemaname, matviewname
                FROM pg_matviews
                WHERE schemaname = ANY(%s)
                ORDER BY schemaname, matviewname
                """,
                (list(schemas),),
            )
            materialized_views = cur.fetchall()

        if not materialized_views:
            print(
                "[MATVIEW] No hay materialized views en: "
                + ", ".join(schemas)
                + ". Las VIEW normales leen datos actuales automáticamente."
            )
            return 0

        for schema_name, view_name in materialized_views:
            print(f"[MATVIEW] refresh {schema_name}.{view_name}")
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("REFRESH MATERIALIZED VIEW {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(view_name),
                    )
                )
            conn.commit()

    print(f"[MATVIEW] actualizadas: {len(materialized_views)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
