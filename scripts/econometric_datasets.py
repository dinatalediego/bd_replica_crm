"""Install via schema_sync; refresh locally or import documented external evidence."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description='Datasets econométricos de Medallio local')
    sub=parser.add_subparsers(dest='command',required=True)
    refresh=sub.add_parser('refresh')
    refresh.add_argument('--once-per-day',action='store_true')
    refresh.add_argument('--backfill',action='store_true')
    imp=sub.add_parser('import-csv')
    imp.add_argument('--kind',choices=('mercado','intervenciones','ofertas','proyecto_mercado'),required=True)
    imp.add_argument('--file',type=Path,required=True)
    sub.add_parser('status')
    args=parser.parse_args(argv)
    from replica_cygnus.connections import connect_postgres
    from replica_cygnus.settings import load_settings
    from replica_cygnus.econometric_datasets.service import run
    root=Path(__file__).resolve().parents[1]
    with connect_postgres(load_settings(root,require_source=False)) as conn:
        if args.command=='refresh':
            print(json.dumps(run(conn,root,once_per_day=args.once_per_day,backfill=args.backfill),ensure_ascii=False))
        elif args.command=='import-csv':
            from replica_cygnus.econometric_datasets.imports import import_csv
            print(json.dumps(import_csv(conn,args.kind,args.file),ensure_ascii=False))
        else:
            with conn.cursor() as cur:
                for title,query in (
                    ('Ejecuciones','SELECT run_id,started_at,finished_at,status,backfill,detail FROM model_control.econometria_runs ORDER BY run_id DESC LIMIT 5'),
                    ('Fuentes','SELECT * FROM model_control.econometria_fuentes ORDER BY fuente'),
                    ('Cobertura','SELECT * FROM analytics.v_econometria_cobertura ORDER BY codigo_proyecto,evidencia')):
                    cur.execute(query)
                    print(title)
                    for row in cur.fetchall(): print(row)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
