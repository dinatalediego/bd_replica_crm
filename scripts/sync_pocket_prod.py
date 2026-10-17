from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from replica_cygnus.pocket_export import SOURCE_FIELDS, build_rows, health_score, latest_rows


SOURCE_SQL = """
SELECT
    periodo_mes,
    codigo_proyecto,
    nombre_proyecto,
    primera_fecha_observada,
    ultima_fecha_observada,
    stock_inicial,
    altas_mes,
    separaciones_brutas_mes,
    caidas_mes,
    separaciones_netas_mes,
    ventas_minutas_mes,
    stock_final,
    absorcion_bruta_mes,
    absorcion_neta_mes,
    absorcion_neta_6m,
    stock_disponible_actual,
    cobertura_stock_disponible_ratio,
    ledger_reconcilia_estado_actual,
    calidad_stock_historico,
    metodo_stock_historico,
    metodo_movimiento,
    metodo_venta,
    mes_parcial,
    fecha_corte
FROM analytics.v_pocket_commercial_project_month
WHERE periodo_mes >= date_trunc('month', (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date) - interval '36 months'
ORDER BY codigo_proyecto, periodo_mes
"""

INSERT_MONTH_SQL = """
INSERT INTO public.pocket_project_month (
    project_ref, project_name, period_month, source_cutoff, is_partial,
    stock_open, gross_separations, falls, net_separations, sales_minutas,
    stock_close, gross_absorption, net_absorption, net_absorption_6m,
    current_stock, stock_coverage, current_state_reconciled, quality_status, synced_at
)
VALUES (
    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
)
"""

INSERT_SUMMARY_SQL = """
INSERT INTO public.pocket_project_summary (
    project_ref, project_name, stage, stock, sales_month, absorption,
    amount_to_sell, months_to_zero, price_m2, health_score, updated_at
)
VALUES (%s,%s,'COMMERCIAL OBSERVED',%s,%s,%s,0,NULL,NULL,%s,now())
"""

FORBIDDEN_COLUMN_SQL = """
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name LIKE 'pocket_%'
  AND lower(column_name) ~
      '(cliente|client|lead|dni|document|telefono|phone|celular|correo|email|direccion|address|nota|note|coment|conversation|grabacion|recording|proforma|unidad|asesor)'
ORDER BY table_name, ordinal_position
"""

ANON_GRANT_SQL = """
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee='anon'
  AND table_schema='public'
  AND table_name LIKE 'pocket_%'
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Export only sanitized project-month commercial aggregates to isolated Medallio Pocket Supabase.'
    )
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def read_source(source_dsn: str) -> list[dict]:
    with psycopg.connect(
        source_dsn,
        application_name='medallio_pocket_source',
        options='-c default_transaction_read_only=on',
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(SOURCE_SQL)
            rows = cur.fetchall()
            if tuple(rows[0].keys()) != SOURCE_FIELDS if rows else False:
                raise RuntimeError('Unexpected source column order/contract')
            return rows


def validate_target(target: psycopg.Connection) -> None:
    with target.cursor() as cur:
        cur.execute(FORBIDDEN_COLUMN_SQL)
        forbidden = cur.fetchall()
        if forbidden:
            raise RuntimeError(f'Pocket target contains forbidden columns: {forbidden}')
        cur.execute(ANON_GRANT_SQL)
        anon_grants = cur.fetchall()
        if anon_grants:
            raise RuntimeError(f'anon has Pocket privileges: {anon_grants}')


def sync_target(target_dsn: str, rows) -> None:
    latest = latest_rows(rows)
    source_cutoff = max(row.source_cutoff for row in rows)

    with psycopg.connect(target_dsn, application_name='medallio_pocket_target') as target:
        validate_target(target)
        with target.cursor() as cur:
            cur.execute(
                "INSERT INTO private.pocket_sync_runs(source_rows, source_cutoff) VALUES (%s,%s) RETURNING sync_run_id",
                (len(rows), source_cutoff),
            )
            sync_run_id = int(cur.fetchone()[0])

            # Atomic snapshot replacement. Readers keep seeing the previous committed snapshot
            # until this transaction commits.
            cur.execute('TRUNCATE TABLE public.pocket_project_month, public.pocket_project_summary')
            cur.executemany(INSERT_MONTH_SQL, [row.as_db_tuple() for row in rows])
            cur.executemany(
                INSERT_SUMMARY_SQL,
                [
                    (
                        row.project_ref,
                        row.project_name,
                        row.current_stock if row.current_stock is not None else row.stock_close,
                        row.sales_minutas,
                        row.net_absorption if row.net_absorption is not None else 0,
                        health_score(row),
                    )
                    for row in latest
                ],
            )
            cur.execute(
                """
                UPDATE private.pocket_sync_runs
                   SET finished_at=now(), status='success', target_rows=%s
                 WHERE sync_run_id=%s
                """,
                (len(rows), sync_run_id),
            )
        target.commit()
        validate_target(target)


def main() -> int:
    args = parse_args()
    source_dsn = os.getenv('MEDALLIO_DSN')
    target_dsn = os.getenv('POCKET_SUPABASE_DB_URL')
    secret_raw = os.getenv('POCKET_PROJECT_HMAC_KEY')

    if not source_dsn:
        raise SystemExit('Falta MEDALLIO_DSN')
    if not secret_raw or len(secret_raw.encode('utf-8')) < 32:
        raise SystemExit('Falta POCKET_PROJECT_HMAC_KEY (minimo 32 bytes)')

    source_rows = read_source(source_dsn)
    rows = build_rows(source_rows, secret_raw.encode('utf-8'))
    projects = len({row.project_ref for row in rows})
    closed = sum(not row.is_partial for row in rows)
    print(f'Pocket aggregate: rows={len(rows)} projects={projects} closed_month_rows={closed}')
    print(f'Source cutoff: {max(row.source_cutoff for row in rows)}')

    if args.dry_run:
        return 0
    if not target_dsn:
        raise SystemExit('Falta POCKET_SUPABASE_DB_URL')

    sync_target(target_dsn, rows)
    print('Medallio Pocket PROD sync: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
