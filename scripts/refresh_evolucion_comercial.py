"""Refresh local commercial panels and preserve one price observation per day."""
from pathlib import Path
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main():
    settings = load_settings(Path(__file__).resolve().parents[1], require_source=False)
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SET LOCAL statement_timeout = '20min'")
            cur.execute('SELECT analytics.refresh_evolucion_comercial()')
            cur.execute('''SELECT count(DISTINCT codigo_proyecto),count(*),max(fecha_corte)
                           FROM analytics.comercial_proyecto_mes''')
            result = cur.fetchone()
        conn.commit()
    print(f'Proyectos={result[0]} | filas proyecto-mes={result[1]} | corte={result[2]}')


if __name__ == '__main__':
    main()
