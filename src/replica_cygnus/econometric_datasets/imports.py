"""Explicit, validated evidence imports; no guessed dates, currencies or prices."""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from psycopg import sql

CONTRACTS = {
 'mercado': ('analytics.contexto_mercado_mes', ('mercado','indicador','periodo_mes','publicado_at','valor','unidad','fuente')),
 'intervenciones': ('analytics.intervencion_comercial', ('clave_fuente','codigo_proyecto','tipo','inicio','fin','disponible_desde','descripcion','inversion','moneda','fuente')),
 'ofertas': ('analytics.historial_oferta_unidad', ('codigo_unidad','codigo_proyecto','tipo_precio','fecha_referencia','disponible_desde','precio','moneda','area_total','descuento','fuente','clave_fuente','calidad')),
 'proyecto_mercado': ('analytics.proyecto_mercado_econometria', ('codigo_proyecto','mercado')),
}
OPTIONAL={'fin','inversion','area_total','descuento'}
DATE_FIELDS={'periodo_mes','inicio','fin','fecha_referencia'}
TIME_FIELDS={'publicado_at','disponible_desde'}
NUM_FIELDS={'valor','inversion','precio','area_total','descuento'}


def parse_rows(kind: str,path: Path):
    _,columns=CONTRACTS[kind]
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not set(columns)<=set(reader.fieldnames or []):
            raise ValueError('Faltan columnas del contrato: '+','.join(sorted(set(columns)-set(reader.fieldnames or []))))
        result=[]
        for n,row in enumerate(reader,2):
            out={}
            for col in columns:
                v=(row.get(col) or '').strip()
                if not v:
                    if col not in OPTIONAL: raise ValueError(f'Fila {n}: {col} obligatorio')
                    out[col]=None;continue
                if col in DATE_FIELDS: v=date.fromisoformat(v)
                elif col in TIME_FIELDS:
                    v=datetime.fromisoformat(v.replace('Z','+00:00'))
                    if v.tzinfo is None: raise ValueError(f'Fila {n}: {col} requiere zona horaria')
                elif col in NUM_FIELDS:
                    try: v=Decimal(v)
                    except InvalidOperation as exc: raise ValueError(f'Fila {n}: número inválido') from exc
                    if not v.is_finite(): raise ValueError(f'Fila {n}: valor no finito')
                out[col]=v
            if kind=='mercado' and out['periodo_mes'].day!=1:
                raise ValueError('periodo_mes debe ser primer día del mes')
            if kind=='ofertas' and (out['tipo_precio'] not in {'LISTA','OFERTADO','CIERRE'} or out['precio']<=0):
                raise ValueError('Tipo de precio inválido o precio no positivo')
            if kind=='ofertas':
                # Imported history is diagnostic unless independently audited, never model-time evidence.
                out['calidad']='IMPORTADO_DOCUMENTAL_PENDIENTE_AUDITORIA'
            result.append(tuple(out[c] for c in columns))
        return columns,result


def import_csv(conn,kind,path):
    columns,rows=parse_rows(kind,path)
    relation,_=CONTRACTS[kind]
    table=sql.Identifier(*relation.split('.'))
    query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING').format(
        table,sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
    with conn.cursor() as cur:
        # Reject conflicting duplicates rather than silently overwriting dated evidence.
        keys={'mercado':('mercado','indicador','periodo_mes','publicado_at'),
              'intervenciones':('clave_fuente',),'ofertas':('fuente','clave_fuente','tipo_precio'),
              'proyecto_mercado':('codigo_proyecto',)}[kind]
        inserted=0
        for row in rows:
            values=dict(zip(columns,row))
            if 'codigo_proyecto' in values:
                cur.execute('SELECT 1 FROM analytics.absorcion_inicio_proyecto WHERE codigo_proyecto=%s',(values['codigo_proyecto'],))
                if cur.fetchone() is None: raise ValueError('Proyecto no registrado en universo comercial')
            if kind=='ofertas':
                cur.execute('SELECT 1 FROM analytics.v_absorcion_ventas_unidad WHERE codigo_unidad=%s AND codigo_proyecto=%s',(values['codigo_unidad'],values['codigo_proyecto']))
                if cur.fetchone() is None: raise ValueError('Unidad/proyecto fuera del universo habilitado')
            where=sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in keys)
            cur.execute(sql.SQL('SELECT {} FROM {} WHERE {}').format(sql.SQL(',').join(map(sql.Identifier,columns)),table,where),tuple(values[k] for k in keys))
            previous=cur.fetchone()
            if previous is not None:
                if tuple(previous)!=tuple(row): raise ValueError('Clave existente con contenido distinto: use una nueva versión documentada')
                continue
            cur.execute(query,row);inserted+=cur.rowcount
    conn.commit()
    return {'rows_read':len(rows),'inserted':inserted}
