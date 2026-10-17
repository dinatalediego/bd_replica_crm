"""Refresh local commercial panels and preserve one price observation per day."""
from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once-per-day",
        action="store_true",
        help="Omite el refresh si todo comercial_proyecto_mes ya tiene corte de hoy en Lima.",
    )
    args = parser.parse_args(argv)

    settings = load_settings(Path(__file__).resolve().parents[1], require_source=False)
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SET LOCAL statement_timeout = '20min'")
            cur.execute('''
                SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date,
                       count(*), min(fecha_corte), max(fecha_corte)
                FROM analytics.comercial_proyecto_mes
            ''')
            today, row_count, min_cutoff, max_cutoff = cur.fetchone()
            if (
                args.once_per_day
                and row_count > 0
                and min_cutoff == today
                and max_cutoff == today
            ):
                conn.rollback()
                print(
                    f'SKIP_ALREADY_TODAY | filas={row_count} | corte={max_cutoff}'
                )
                return 0

            cur.execute('SELECT analytics.refresh_evolucion_comercial()')
            cur.execute('''
                SELECT count(DISTINCT codigo_proyecto),count(*),
                       min(fecha_corte),max(fecha_corte)
                FROM analytics.comercial_proyecto_mes
            ''')
            projects, rows, min_cutoff, max_cutoff = cur.fetchone()
            if rows == 0 or min_cutoff != max_cutoff:
                raise RuntimeError(
                    'Refresh evolución comercial dejó un corte vacío o inconsistente'
                )
        conn.commit()
    print(
        f'REFRESH_OK | proyectos={projects} | filas proyecto-mes={rows} | corte={max_cutoff}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
