from __future__ import annotations

import csv
from pathlib import Path

from psycopg.rows import dict_row

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


AUDIT_SQL = r"""
WITH extras_ranked AS (
    SELECT
        de.id,
        de.codigo::text AS codigo_proforma,
        lower(de.nombre) AS nombre,
        de.valor,
        de.fecha_actualizacion,
        row_number() OVER (
            PARTITION BY de.codigo, lower(de.nombre)
            ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
        ) AS rn
    FROM raw_cygnus.datos_extras de
    WHERE lower(de.entidad) = 'proforma'
      AND lower(de.nombre) IN (
          'pago_ci',
          'fecha_de_minuta',
          'monto_total_pagado',
          'monto_pagado_de_cuota_inicial'
      )
), extras AS (
    SELECT
        codigo_proforma,
        max(valor) FILTER (WHERE nombre='pago_ci' AND rn=1) AS raw_pago_ci,
        max(valor) FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS raw_fecha_de_minuta,
        max(valor) FILTER (WHERE nombre='monto_total_pagado' AND rn=1) AS raw_monto_total_pagado,
        max(valor) FILTER (WHERE nombre='monto_pagado_de_cuota_inicial' AND rn=1) AS raw_monto_pagado_de_cuota_inicial
    FROM extras_ranked
    GROUP BY codigo_proforma
), parsed AS (
    SELECT
        e.*,
        analytics.try_parse_business_date(e.raw_fecha_de_minuta) AS raw_fecha_pago_ci,
        analytics.try_parse_numeric(e.raw_monto_total_pagado) AS raw_monto_total_pagado_num,
        analytics.try_parse_numeric(e.raw_monto_pagado_de_cuota_inicial) AS raw_monto_pagado_de_cuota_inicial_num
    FROM extras e
)
SELECT
    f.separation_id,
    f.codigo_proforma,
    f.codigo_unidad,
    f.codigo_proyecto,
    f.asesor,
    f.fecha_separacion,
    f.observed_at,
    f.proforma_first_seen_at,
    f.days_since_separation,
    f.days_since_last_interaction,
    f.interaction_count_14d,
    c.pago_ci_marker_raw AS core_pago_ci_marker_raw,
    c.pago_ci_marker_confirmado AS core_pago_ci_marker_confirmado,
    c.fecha_pago_ci AS core_fecha_pago_ci,
    c.monto_total_pagado AS core_monto_total_pagado,
    c.monto_pagado_de_cuota_inicial AS core_monto_pagado_de_cuota_inicial,
    c.monto_pagado_cuota_inicial AS core_monto_pagado_cuota_inicial,
    c.monto_pago_ci_positivo AS core_monto_pago_ci_positivo,
    c.evidencia_pago_ci_confirmada AS core_evidencia_pago_ci_confirmada,
    p.raw_pago_ci,
    p.raw_fecha_de_minuta,
    p.raw_fecha_pago_ci,
    p.raw_monto_total_pagado,
    p.raw_monto_total_pagado_num,
    p.raw_monto_pagado_de_cuota_inicial,
    p.raw_monto_pagado_de_cuota_inicial_num,
    coalesce(p.raw_monto_total_pagado_num, p.raw_monto_pagado_de_cuota_inicial_num) AS raw_monto_pago_ci,
    (
        p.raw_fecha_pago_ci IS NOT NULL
        OR lower(btrim(coalesce(p.raw_pago_ci,''))) = lower('Pagó cuota inicial (Minuta)')
        OR coalesce(p.raw_monto_total_pagado_num, p.raw_monto_pagado_de_cuota_inicial_num) > 0
    ) AS raw_payment_evidence_confirmed,
    (
        (p.raw_monto_total_pagado IS NOT NULL AND btrim(p.raw_monto_total_pagado) <> '' AND p.raw_monto_total_pagado_num IS NULL)
        OR
        (p.raw_monto_pagado_de_cuota_inicial IS NOT NULL AND btrim(p.raw_monto_pagado_de_cuota_inicial) <> '' AND p.raw_monto_pagado_de_cuota_inicial_num IS NULL)
    ) AS raw_payment_amount_parse_error,
    (
        (
            p.raw_fecha_pago_ci IS NOT NULL
            OR lower(btrim(coalesce(p.raw_pago_ci,''))) = lower('Pagó cuota inicial (Minuta)')
            OR coalesce(p.raw_monto_total_pagado_num, p.raw_monto_pagado_de_cuota_inicial_num) > 0
        )
        AND NOT coalesce(c.evidencia_pago_ci_confirmada, false)
    ) AS raw_core_payment_mismatch
FROM features.separation_fall_risk_current f
LEFT JOIN core.fact_ciclo_comercial_unidad c
  ON c.codigo_proforma = f.codigo_proforma
 AND c.codigo_unidad = f.codigo_unidad
LEFT JOIN parsed p
  ON p.codigo_proforma = f.codigo_proforma
ORDER BY
    raw_payment_evidence_confirmed DESC,
    raw_core_payment_mismatch DESC,
    f.days_since_separation DESC,
    f.separation_id;
"""


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = load_settings()
    reports = settings.project_root / 'reports'

    with connect_postgres(settings) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(AUDIT_SQL)
            rows = [dict(row) for row in cur.fetchall()]

    unsafe = [row for row in rows if row.get('raw_payment_evidence_confirmed')]
    mismatches = [row for row in rows if row.get('raw_core_payment_mismatch')]
    parse_errors = [row for row in rows if row.get('raw_payment_amount_parse_error')]

    all_path = reports / 'risk_candidate_payment_evidence_audit.csv'
    unsafe_path = reports / 'risk_candidates_with_raw_payment_evidence.csv'
    mismatch_path = reports / 'risk_candidate_raw_core_payment_mismatches.csv'
    parse_path = reports / 'risk_candidate_payment_parse_errors.csv'

    write_csv(all_path, rows)
    write_csv(unsafe_path, unsafe)
    write_csv(mismatch_path, mismatches)
    write_csv(parse_path, parse_errors)

    print('Payment-evidence audit completado')
    print(f'  candidates: {len(rows)}')
    print(f'  candidates_with_raw_payment_evidence: {len(unsafe)}')
    print(f'  raw_core_payment_mismatches: {len(mismatches)}')
    print(f'  raw_payment_amount_parse_errors: {len(parse_errors)}')
    print(f'  detalle: {all_path}')
    print(f'  evidencia RAW dentro de candidatos: {unsafe_path}')
    print(f'  mismatches RAW vs CORE: {mismatch_path}')
    print(f'  errores parse monto: {parse_path}')

    if unsafe or mismatches or parse_errors:
        print('Gate de auditoría NO aprobado: todavía existe evidencia de pago o mismatch dentro del scoring.')
        return 1

    print('Gate de auditoría APROBADO: ningún candidato conserva evidencia RAW de pago de inicial.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
