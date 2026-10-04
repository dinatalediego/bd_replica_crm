from __future__ import annotations

import argparse
import math
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from replica_cygnus.commercial_forecasting.core import Config, validate_panel
from replica_cygnus.commercial_forecasting.service import (
    audit_artifacts, dumps, ensure_schema, execute, measure, read_source, save_snapshot, store_run, synthetic_panel,
)
from replica_cygnus.commercial_forecasting.robustness import verify_integrity
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


def parser():
    p = argparse.ArgumentParser(description='Forecasting Cygnus: diagnóstico, entrenamiento, evidencia y seguimiento')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('demo', 'run', 'csv'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--output', type=Path, default=ROOT/'artifacts/commercial_forecasting')
        cmd.add_argument('--backtest-origins', type=int, default=24)
        cmd.add_argument('--test-origins', type=int, default=6)
        if name == 'run':
            cmd.add_argument('--once-per-month', action='store_true')
        if name == 'csv':
            cmd.add_argument('--input', type=Path, required=True)
    sub.add_parser('init')
    sub.add_parser('capture')
    sub.add_parser('measure')
    sub.add_parser('status')
    audit = sub.add_parser('audit')
    audit.add_argument('--artifacts', type=Path, required=True)
    audit.add_argument('--output', type=Path, default=ROOT/'artifacts/commercial_forecasting_audits')
    verify = sub.add_parser('verify')
    verify.add_argument('--artifacts', type=Path, required=True)
    goal = sub.add_parser('goal')
    goal.add_argument('--origin', required=True)
    goal.add_argument('--project', required=True)
    goal.add_argument('--horizon', type=int, choices=range(1, 7), required=True)
    goal.add_argument('--sales', type=float, required=True)
    goal.add_argument('--owner', required=True)
    action = sub.add_parser('action')
    action.add_argument('--run-id', required=True)
    action.add_argument('--project', required=True)
    action.add_argument('--horizon', type=int, choices=range(1, 7), required=True)
    action.add_argument('--model', required=True)
    action.add_argument('--owner', required=True)
    action.add_argument('--taken', required=True)
    action.add_argument('--cost', type=float, default=0)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == 'audit':
        directory, report = audit_artifacts(args.artifacts, args.output)
        print(dumps(report))
        print(directory/'report.html')
        return 0
    if args.command == 'verify':
        result = verify_integrity(args.artifacts)
        print(dumps(result))
        return 0 if result['status'] == 'VERIFIED' else 2
    if args.command in ('demo', 'csv'):
        panel = synthetic_panel() if args.command == 'demo' else pd.read_csv(args.input, dtype={'project': str})
        directory, manifest, _, _ = execute(panel, ROOT, args.output,
            Config(backtest_origins=args.backtest_origins, test_origins=args.test_origins), synthetic=args.command == 'demo')
        print(f"{manifest['evidence_level']} | run={manifest['run_id']} | selected={manifest['selected_model']}")
        print(directory/'report.html')
        return 0
    settings = load_settings(ROOT, require_source=False)
    with connect_postgres(settings) as conn:
        ensure_schema(conn, ROOT)
        if args.command == 'init':
            print('Esquema de evidencia listo. Sin consultas a Redshift.')
        elif args.command in ('capture', 'run'):
            if args.command == 'run':
                with conn.cursor() as cur:
                    cur.execute('SELECT pg_try_advisory_lock(63409127)')
                    if not cur.fetchone()[0]:
                        print('Otra ejecución de forecasting está activa; se omite este intento.')
                        return 0
                    expected = (pd.Timestamp(datetime.now(ZoneInfo('America/Lima')).date()).to_period('M')-1).to_timestamp()
                    if args.once_per_month:
                        cur.execute("SELECT count(*) FROM model_control.commercial_forecast_runs WHERE manifest->>'origin'=%s", (str(expected.date()),))
                        if cur.fetchone()[0]:
                            print('Ya existe una ejecución para el último mes cerrado. No se reentrena.')
                            return 0
            panel, quality = validate_panel(read_source(conn))
            if args.command == 'run' and panel.month.max() != expected:
                raise ValueError('La fuente no llega al último mes cerrado; actualizar Medallio antes de entrenar')
            snapshot_id = save_snapshot(conn, panel, quality)
            # Keep snapshot even when history is too short to fit/backtest.
            conn.commit()
            print(f"Snapshot={snapshot_id} | projects={quality['projects']} | hash={quality['sha256']}")
            if args.command == 'run':
                directory, manifest, future, bt = execute(panel, ROOT, args.output,
                    Config(backtest_origins=args.backtest_origins, test_origins=args.test_origins), snapshot_id=snapshot_id,
                    snapshot_context=quality.get('snapshot_comparison'))
                store_run(conn, directory, manifest, future, bt)
                conn.commit()
                print(f"Run={manifest['run_id']} | selected={manifest['selected_model']} | SHADOW")
                print(directory/'report.html')
                print(f'Outcomes maduros registrados: {measure(conn)}')
        elif args.command == 'measure':
            print(f'Outcomes maduros registrados: {measure(conn)}')
        elif args.command == 'goal':
            origin = pd.Timestamp(args.origin)
            if origin.day != 1 or not math.isfinite(args.sales) or args.sales < 0 or not args.owner.strip():
                raise ValueError('Meta: origin debe ser primer día del mes; sales >= 0 y owner obligatorio')
            with conn.cursor() as cur:
                cur.execute('''INSERT INTO decision_intelligence.commercial_forecast_goals
                  (origin,project,horizon,target_sales,owner) VALUES (%s,%s,%s,%s,%s)
                  ON CONFLICT (origin,project,horizon) DO UPDATE
                  SET target_sales=excluded.target_sales,owner=excluded.owner''',
                  (origin.date(), args.project, args.horizon, args.sales, args.owner))
            print('Meta registrada; horizonte acumulado desde el mes siguiente al corte.')
        elif args.command == 'action':
            if not math.isfinite(args.cost) or args.cost < 0 or not args.owner.strip() or not args.taken.strip():
                raise ValueError('Acción: costo no negativo, responsable y descripción obligatorios')
            action_id = str(uuid4())
            with conn.cursor() as cur:
                cur.execute('''INSERT INTO decision_intelligence.commercial_forecast_actions
                  (action_id,run_id,project,horizon,model,owner,action,cost)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                  (action_id,args.run_id,args.project,args.horizon,args.model,args.owner,args.taken,args.cost))
            print(f'Acción registrada: {action_id}')
        elif args.command == 'status':
            with conn.cursor() as cur:
                cur.execute('''SELECT run_id,created_at,selected_model,evidence_level,artifact_path
                  FROM model_control.commercial_forecast_runs ORDER BY created_at DESC LIMIT 10''')
                print(dumps([dict(zip(['run_id','created_at','selected_model','evidence_level','artifact_path'],
                                     [str(v) for v in row])) for row in cur.fetchall()]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
