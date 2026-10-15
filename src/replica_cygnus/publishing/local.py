"""Opt-in local PostgreSQL boundary. No Redshift access, no PII queries."""
from decimal import Decimal
from .contracts import validate_snapshot


def capture_snapshot(conn, as_of):
    with conn.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cur.execute("SET LOCAL statement_timeout = '30s'")
        # Contract is an installed, reconciled aggregate; never query raw CRM.
        cur.execute('''SELECT codigo_proyecto,periodo_mes,stock_inicial,ventas_mes,
                              stock_final,unidades_revision
                       FROM analytics.comercial_proyecto_mes
                       WHERE NOT mes_parcial AND periodo_mes < date_trunc('month',%s::date)
                         AND codigo_proyecto <> 'CAM'
                       ORDER BY codigo_proyecto,periodo_mes LIMIT 10001''',(as_of,))
        records=cur.fetchall()
    rows=[dict(zip(('project','period','stock_open','sales','stock_close','review_units'),
                   (v.isoformat() if hasattr(v,'isoformat') else float(v) if isinstance(v,Decimal) else v for v in row))) for row in records]
    snapshot=dict(schema_version='1.0.0',source='analytics.comercial_proyecto_mes',
                  semantics='RECONSTRUCTED_REVISED_HISTORY',as_of=as_of,rows=rows)
    validate_snapshot(snapshot)
    return snapshot


def register_bundle(conn, manifest, packs, archive_sha256):
    """One transactional insert, idempotent only for the exact same artifact."""
    from psycopg.types.json import Jsonb
    from .contracts import validate_bundle, validate
    validate('manifest',manifest); validate_bundle(packs)
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO publish.product_release
            (archive_sha256,product_id,product_version,classification,manifest,payload)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(archive_sha256) DO NOTHING''',
            (archive_sha256,manifest['pack_id'],manifest['pack_version'],manifest['classification'],Jsonb(manifest),Jsonb(packs)))


def record_decision_event(conn, event):
    """Append feedback locally; never edits an issued story or claims causality."""
    from psycopg.types.json import Jsonb
    from .contracts import validate, digest
    validate('decision-event', event)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO publish.decision_event
            (event_sha256,archive_sha256,decision_id,event_type,occurred_at,payload)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(event_sha256) DO NOTHING""",
            (digest(event),event['archive_sha256'],event['decision_id'],event['event_type'],
             event['occurred_at'],Jsonb(event)))
