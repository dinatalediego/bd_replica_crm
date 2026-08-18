from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["codigo_proforma"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = load_settings()
    report_path = settings.project_root / "reports" / "pago_ci_semantics_profile.csv"

    sql = """
        WITH extras AS (
            SELECT
                de.codigo::text AS codigo_proforma,
                lower(de.nombre) AS nombre,
                de.valor,
                de.id,
                de.fecha_actualizacion,
                row_number() OVER (
                    PARTITION BY de.codigo, lower(de.nombre)
                    ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
                ) AS rn
            FROM raw_cygnus.datos_extras de
            WHERE lower(de.entidad)='proforma'
              AND lower(de.nombre) IN ('pago_ci','fecha_de_minuta')
        ), pivot AS (
            SELECT
                codigo_proforma,
                max(valor) FILTER (WHERE nombre='pago_ci' AND rn=1) AS pago_ci_marker,
                max(id) FILTER (WHERE nombre='pago_ci' AND rn=1) AS pago_ci_marker_id,
                max(valor) FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS fecha_pago_ci_raw,
                max(id) FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS fecha_pago_ci_id,
                max(analytics.try_parse_business_date(valor))
                    FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS fecha_pago_ci
            FROM extras
            GROUP BY codigo_proforma
        )
        SELECT
            codigo_proforma,
            pago_ci_marker,
            pago_ci_marker_id,
            fecha_pago_ci_raw,
            fecha_pago_ci_id,
            fecha_pago_ci,
            CASE
                WHEN pago_ci_marker IS NOT NULL
                 AND btrim(pago_ci_marker)<>''
                 AND lower(btrim(pago_ci_marker)) = lower('Pagó cuota inicial (Minuta)')
                    THEN 'CONFIRMED_MARKER'
                WHEN pago_ci_marker IS NOT NULL AND btrim(pago_ci_marker)<>''
                    THEN 'UNKNOWN_MARKER'
                ELSE 'NO_MARKER'
            END AS marker_status,
            CASE
                WHEN pago_ci_marker IS NOT NULL AND btrim(pago_ci_marker)<>''
                 AND fecha_pago_ci IS NOT NULL THEN 'MARKER_AND_DATE'
                WHEN pago_ci_marker IS NOT NULL AND btrim(pago_ci_marker)<>''
                 AND fecha_pago_ci IS NULL THEN 'MARKER_WITHOUT_DATE'
                WHEN (pago_ci_marker IS NULL OR btrim(pago_ci_marker)='')
                 AND fecha_pago_ci IS NOT NULL THEN 'DATE_WITHOUT_MARKER'
                ELSE 'NO_EVIDENCE'
            END AS pairing_status
        FROM pivot
        WHERE (pago_ci_marker IS NOT NULL AND btrim(pago_ci_marker)<>'')
           OR fecha_pago_ci_raw IS NOT NULL
        ORDER BY pairing_status, codigo_proforma
    """

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            names = [d.name for d in cur.description]
            rows = [dict(zip(names, row)) for row in cur.fetchall()]

    _write_csv(report_path, rows)

    pairing_counts: dict[str, int] = {}
    marker_counts: dict[str, int] = {}
    unparseable_dates = 0
    for row in rows:
        pairing = str(row["pairing_status"])
        marker = str(row["marker_status"])
        pairing_counts[pairing] = pairing_counts.get(pairing, 0) + 1
        marker_counts[marker] = marker_counts.get(marker, 0) + 1
        if row.get("fecha_pago_ci_raw") not in (None, "") and row.get("fecha_pago_ci") is None:
            unparseable_dates += 1

    print("Perfil semántico pago_ci / fecha_de_minuta completado")
    print(f"  detalle: {report_path}")
    print("  pairing:")
    for key, value in sorted(pairing_counts.items()):
        print(f"    {key}: {value}")
    print("  marker status:")
    for key, value in sorted(marker_counts.items()):
        print(f"    {key}: {value}")
    print(f"  fecha_pago_ci_no_parseable: {unparseable_dates}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
