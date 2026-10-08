from __future__ import annotations

import json
from pathlib import Path
from psycopg import sql


def collect_demand(conn, config_path: Path):
    """Aggregate locally; no documents or other customer PII leave the source query."""
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    metrics = {}
    statuses = {}
    for name in ('asignaciones', 'captacion', 'proformas', 'interacciones'):
        spec = cfg.get(name, {})
        if not spec.get('enabled'):
            statuses[name] = 'DISABLED_CONTRACT_REQUIRED'
            continue
        required_keys = {'schema', 'table', 'project', 'date', 'id'}
        if not required_keys <= spec.keys():
            raise ValueError(f'Contrato incompleto: {name}')
        required = {spec[k] for k in ('project', 'date', 'id')}
        required |= {spec[k] for k in ('client', 'unit', 'visit_column') if spec.get(k)}
        with conn.cursor() as cur:
            cur.execute('''SELECT column_name FROM information_schema.columns
                WHERE table_schema=%s AND table_name=%s''', (spec['schema'], spec['table']))
            actual = {r[0] for r in cur.fetchall()}
            if not required <= actual:
                statuses[name] = 'MISSING_COLUMNS:' + ','.join(sorted(required - actual))
                continue
            fields = {k: sql.Identifier('r', spec[k]) for k in ('project', 'date', 'id')}
            client = sql.SQL("count(DISTINCT NULLIF(btrim({}::text),''))").format(sql.Identifier('r', spec['client'])) if spec.get('client') else sql.SQL('NULL::bigint')
            scope = sql.SQL('')
            if spec.get('unit'):
                scope = sql.SQL('AND EXISTS(SELECT 1 FROM analytics.v_absorcion_ventas_unidad u WHERE u.codigo_unidad={}::text)').format(sql.Identifier('r',spec['unit']))
            # Strict date-typed source contract. Bad/unparseable fields fail visibly, not zero-fill.
            query = sql.SQL('''SELECT {project}::text,date_trunc('week',{date}::timestamp)::date,
                count(DISTINCT {id}),{client},count(*) FILTER(WHERE {date} IS NULL)
                FROM {table} r WHERE {date}::date <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                {scope} GROUP BY 1,2''').format(**fields, client=client,
                    table=sql.Identifier(spec['schema'],spec['table']),scope=scope)
            cur.execute(query)
            rows = cur.fetchall()
            metrics[name] = {(r[0],r[1]): (r[2],r[3]) for r in rows}
            statuses[name] = 'OK'
            # Do not call an arbitrary interaction a visit.
            if name == 'interacciones' and spec.get('visit_column'):
                if not isinstance(spec.get('visit_values'), list) or not spec['visit_values']:
                    raise ValueError('visit_values debe contener las etiquetas verificadas de visita')
                vq = sql.SQL('''SELECT {project}::text,date_trunc('week',{date}::timestamp)::date,count(DISTINCT {id})
                 FROM {table} r WHERE {date}::date <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                 AND {visit}::text=ANY(%s) {scope} GROUP BY 1,2''').format(**fields,
                 table=sql.Identifier(spec['schema'],spec['table']),visit=sql.Identifier('r',spec['visit_column']),scope=scope)
                cur.execute(vq,(spec['visit_values'],))
                metrics['visitas'] = {(r[0],r[1]): (r[2],None) for r in cur.fetchall()}
                statuses['visitas']='OK'
    with conn.cursor() as cur:
        for name,status in statuses.items():
            cur.execute('''INSERT INTO model_control.econometria_fuentes(fuente,estado,detalle)
                VALUES(%s,%s,%s) ON CONFLICT(fuente) DO UPDATE SET estado=excluded.estado,
                detalle=excluded.detalle,checked_at=clock_timestamp()''',
                (name,'OK' if status=='OK' else 'PENDIENTE',status))
        starts={}
        for data in metrics.values():
            for project,week in data:
                if project is not None and week is not None:
                    starts[project]=min(starts.get(project,week),week)
        cur.execute('DROP TABLE IF EXISTS pg_temp.econom_demand_start')
        cur.execute('CREATE TEMP TABLE econom_demand_start(project text PRIMARY KEY,start_date date) ON COMMIT DROP')
        cur.executemany('INSERT INTO econom_demand_start VALUES(%s,%s)',list(starts.items()))
        cur.execute('''WITH bounds AS (
            SELECT u.codigo_proyecto,least(min(u.fecha_ingreso_stock),min(s.start_date)) AS inicio
            FROM analytics.v_absorcion_ventas_unidad u LEFT JOIN econom_demand_start s ON s.project=u.codigo_proyecto GROUP BY 1
          ), ev AS (
            SELECT codigo_proyecto,date_trunc('week',fecha_evento)::date AS semana,
            count(*) FILTER(WHERE tipo_evento='SEPARACION') AS separaciones,
            count(*) FILTER(WHERE tipo_evento='MINUTA') AS minutas,
            count(*) FILTER(WHERE tipo_evento='ANULACION') AS anulaciones
            FROM analytics.v_evento_comercial_actual WHERE activo AND fuente='ABSORCION_CICLOS'
            GROUP BY 1,2
          ) SELECT b.codigo_proyecto,w::date,coalesce(e.separaciones,0),coalesce(e.minutas,0),coalesce(e.anulaciones,0)
          FROM bounds b CROSS JOIN LATERAL generate_series(date_trunc('week',b.inicio),
            date_trunc('week',CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima'),interval '1 week') w
          LEFT JOIN ev e ON e.codigo_proyecto=b.codigo_proyecto AND e.semana=w::date''')
        panel=cur.fetchall()
        rows=[]
        def value(source, key, index=0):
            if source not in metrics:
                return None
            project_weeks=[k[1] for k in metrics[source] if k[0]==key[0]]
            if not project_weeks or key[1]<min(project_weeks):
                return None
            return metrics[source].get(key,(0,0))[index]
        for project,week,sep,sales,falls in panel:
            key=(project,week)
            rows.append((project,week,value('asignaciones',key),value('asignaciones',key,1),
                         value('proformas',key),value('interacciones',key),value('visitas',key),
                         sep,sales,falls,json.dumps(statuses),value('captacion',key),value('captacion',key,1)))
        cur.execute('DELETE FROM analytics.panel_demanda_proyecto_semana')
        cur.executemany('''INSERT INTO analytics.panel_demanda_proyecto_semana
          (codigo_proyecto,semana,asignaciones_clientes,clientes_unicos_asignados,proformas,
          interacciones,visitas,separaciones,minutas_brutas,anulaciones,fuentes,leads_creados,clientes_unicos_creados)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)''',rows)
    return statuses


def run(conn, root: Path, *, once_per_day=False, backfill=False):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext('econometric_datasets'))")
        if not cur.fetchone()[0]:
            conn.rollback()
            return {'status':'SKIP_CONCURRENT'}
    run_id=None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS(SELECT 1 FROM model_control.econometria_runs WHERE status='OK')")
            backfill = backfill or not cur.fetchone()[0]
            if once_per_day and not backfill:
                cur.execute('''SELECT EXISTS(SELECT 1 FROM model_control.econometria_runs WHERE status='OK'
                    AND (finished_at AT TIME ZONE 'America/Lima')::date=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date)''')
                if cur.fetchone()[0]:
                    conn.rollback()
                    return {'status':'SKIP_ALREADY_TODAY'}
            cur.execute("INSERT INTO model_control.econometria_runs(status,backfill) VALUES('RUNNING',%s) RETURNING run_id",(backfill,))
            run_id=cur.fetchone()[0]
        conn.commit()
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM analytics.v_absorcion_ventas_unidad')
            if cur.fetchone()[0] == 0:
                raise RuntimeError('Universo comercial vacío: actualizar CORE/absorción antes de capturar')
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SET LOCAL statement_timeout='30min'")
            cur.execute('SELECT analytics.refresh_evolucion_comercial()')
            cur.execute('SELECT analytics.capture_econometric_events()')
            cur.execute('SELECT analytics.capture_econometric_current()')
            cur.execute('SELECT analytics.backfill_econometric_prices()')
            if backfill:
                cur.execute('SELECT analytics.backfill_econometric_stock()')
        statuses=collect_demand(conn,root/'config/econometric_sources.json')
        with conn.cursor() as cur:
            cur.execute('SELECT analytics.build_econometric_datasets(true)')
            cur.execute("UPDATE model_control.econometria_runs SET status='OK',finished_at=clock_timestamp(),detail=%s::jsonb WHERE run_id=%s",(json.dumps(statuses),run_id))
        conn.commit()
        return {'status':'OK','run_id':run_id,'backfill':backfill,'sources':statuses}
    except Exception as exc:
        conn.rollback()
        if run_id is not None:
            with conn.cursor() as cur:
                # Exception type only; raw error text may contain source PII/credentials.
                cur.execute("UPDATE model_control.econometria_runs SET status='FAILED',finished_at=clock_timestamp(),detail=%s::jsonb WHERE run_id=%s",(json.dumps({'error_type':type(exc).__name__}),run_id))
            conn.commit()
        raise
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext('econometric_datasets'))")
        conn.commit()
