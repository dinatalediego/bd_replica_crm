"""Aggregate planning reference. No writes to DB, no experiment activation."""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

COUNTS = ['assignments','first_client_project','first_client_global','first_live','first_inferred',
          'sep_mature','sep_observed','sep_positive','minuta_mature','minuta_observed','minuta_positive']


def wilson(positive, n):
    if not n:
        return None
    z=1.959963984540054
    p=positive/n
    middle=(p+z*z/(2*n))/(1+z*z/n)
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0,middle-radius),min(1,middle+radius)]


def parameters(start: date, end: date):
    if not 1 <= (end-start).days <= 1095:
        raise ValueError('Ventana debe tener entre 1 y 1095 días completos')
    lima=ZoneInfo('America/Lima')
    return dict(start_at=datetime.combine(start,time(),lima),end_at=datetime.combine(end,time(),lima),end_day=end)


def collect(conn, root: Path, start: date, end: date):
    # Must use a new connection; do not inherit an ETL transaction.
    params=parameters(start,end)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute("SET LOCAL lock_timeout='5s'")
        cur.execute("SHOW transaction_read_only")
        if cur.fetchone()[0]!='on':
            raise RuntimeError('No se confirmó transacción de solo lectura')
        cur.execute((root/'sql/lead_pilot_history_readonly.sql').read_text(encoding='utf-8'),params)
        return cur.fetchone()[0]


def summarize(payload, start: date, end: date):
    parameters(start,end)
    raw=pd.DataFrame(payload['daily'])
    quality=dict(payload['quality'])
    quality['window_valid_rows']=int(raw.assignments.sum()) if not raw.empty else 0
    quality['reconciled']=(quality['window_source_rows']==quality['window_valid_rows']+quality['invalid_identity_or_project'])
    if not quality['reconciled']:
        raise ValueError('No concilian origen y agregado: detener interpretación')
    projects=[]; daily=[]
    calendar=pd.date_range(start,end-timedelta(days=1),freq='D')
    for project,g in raw.groupby('project') if not raw.empty else []:
        g=g.copy(); g['day']=pd.to_datetime(g.day)
        g=g.set_index('day').reindex(calendar,fill_value=0)
        for col in COUNTS:
            g[col]=pd.to_numeric(g[col]).astype(int)
        row=dict(project=project,calendar_days=len(g),days_without_first_clients=int((g.first_client_project==0).sum()))
        row.update({k:int(g[k].sum()) for k in COUNTS})
        row['repeat_assignments']=row['assignments']-row['first_client_project']
        row['first_clients_per_calendar_day']=float(g.first_client_project.mean())
        row['first_global_clients_per_calendar_day']=float(g.first_client_global.mean())
        row['daily_first_clients_p50']=float(g.first_client_project.median())
        row['daily_first_clients_p90']=float(g.first_client_project.quantile(.9))
        recent=g.tail(min(28,len(g)))
        row['recent_28d_first_clients_per_day']=float(recent.first_client_project.mean())
        for target in ['sep','minuta']:
            n=row[target+'_observed']; m=row[target+'_mature']; y=row[target+'_positive']
            if not 0<=y<=n<=m<=row['first_client_project']:
                raise ValueError('Conteos de etiquetas inconsistentes')
            row[target+'_missing']=m-n
            row[target+'_observed_rate']=y/n if n else None
            row[target+'_wilson95_observed']=wilson(y,n)
            # Planning baseline is blocked if mature data are incomplete.
            row[target+'_complete_cohort_rate']=y/m if m and n==m else None
            row[target+'_missing_bounds']=[y/m,(y+m-n)/m] if m else None
        projects.append(row)
        for day,d in g.iterrows():
            daily.append(dict(project=project,day=day.date().isoformat(),**{k:int(d[k]) for k in COUNTS}))
    return dict(start_inclusive=start.isoformat(),end_exclusive=end.isoformat(),timezone='America/Lima',
        quality=quality,excluded_at_or_after_cutoff=payload['excluded_at_or_after_cutoff'],
        projects=projects,daily=daily,
        interpretation='HISTORICAL_REFERENCE_NOT_PILOT_ELIGIBILITY',
        limitations=[
            'Primera aparición OBSERVADA en la evidencia disponible; no prueba primer contacto real.',
            'Conversión de primera aparición por cliente/proyecto. Global asigna cada cliente a su primer proyecto observado; no sumar únicos por proyecto como únicos globales.',
            'No filtra consentimiento, compra previa, score mínimo ni capacidad comercial: el flujo no equivale a ELIGIBLE_PER_DAY.',
            'Etiquetas almacenadas por fecha de decisión, no por asignación al experimento; no se recalculan ni se certifican procesos.',
            'Los campos LIVE/BACKFILL describen captura; LIVE no garantiza features point-in-time.',
            'Madurez usa fechas de Lima; verificar timezone usado por el refresco de etiquetas existente.',
            'Datos corregidos después del corte pueden estar presentes: fotografía actual, no reconstrucción histórica point-in-time.',
            'Días sin filas cuentan como cero; también pueden reflejar faltantes ETL, cierres o proyectos fuera de operación.',
            'latest_capture no certifica frescura de Redshift; puede cambiar al recapturar.',
            'Comparación origen/destino de este diagnóstico: features.lead_evidence frente a sus agregados; no conciliación Redshift-DW.',
        ])


def markdown_report(result):
    lines=['# Diagnóstico histórico del piloto',
        f"Ventana: {result['start_inclusive']} a {result['end_exclusive']} (fin excluido, Lima).",
        '', 'Referencia histórica; no son resultados de un experimento ni elegibilidad aprobada.', '',
        '| Proyecto | Primeros cliente/proyecto | Flujo/día | Flujo reciente/día | Separación: positivos/observados | Faltantes maduros |',
        '|---|---:|---:|---:|---:|---:|']
    for p in result['projects']:
        label=str(p['project']).replace('|','/').replace('\n',' ')
        lines.append(f"| {label} | {p['first_client_project']} | {p['first_clients_per_calendar_day']:.2f} | {p['recent_28d_first_clients_per_day']:.2f} | {p['sep_positive']}/{p['sep_observed']} | {p['sep_missing']} |")
    lines += ['', '## Conciliación', '', str(result['quality']), '', '## Límites', '']
    lines += ['- '+x for x in result['limitations']]
    lines += ['', '## Siguiente decisión', '',
              'Elegir proyectos y elegibilidad; estimar su flujo real; acordar el MDE comercial. Después calcular muestra y duración. No copiar automáticamente estas tasas o flujos al protocolo.']
    return '\n'.join(lines)+'\n'
