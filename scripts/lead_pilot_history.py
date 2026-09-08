from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings
from replica_cygnus.lead_scoring.history_diagnostic import collect, summarize, markdown_report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Diagnóstico histórico agregado, solo lectura PostgreSQL')
    parser.add_argument('--days',type=int,default=180)
    parser.add_argument('--end',type=date.fromisoformat,help='Fecha final EXCLUIDA; por defecto hoy en Lima')
    args=parser.parse_args(argv)
    end=args.end or datetime.now(ZoneInfo('America/Lima')).date()
    if not 1<=args.days<=1095 or end>datetime.now(ZoneInfo('America/Lima')).date():
        parser.error('days: 1..1095; end no debe ser futuro')
    start=end-timedelta(days=args.days)
    print(f'[history] {start} <= fecha < {end}; solo lectura; límite SQL 60s',flush=True)
    with connect_postgres(load_settings()) as conn:
        data=collect(conn,ROOT,start,end)
    result=summarize(data,start,end)
    result['generated_at']=datetime.now(timezone.utc).isoformat()
    # Only aggregate outputs. Unique directory avoids overwriting a previous run.
    output=ROOT/'reports'/'pilot_history'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8])
    output.mkdir(parents=True)
    (output/'diagnostico.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    (output/'RESUMEN.md').write_text(markdown_report(result),encoding='utf-8')
    print(f"[history] proyectos={len(result['projects'])}; conciliado={result['quality']['reconciled']}; rechazados_identidad_proyecto={result['quality']['invalid_identity_or_project']}",flush=True)
    print(f'[output] {output}')
    print('Compartir diagnostico.json para analizar. No contiene documentos, teléfonos ni nombres de clientes.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
