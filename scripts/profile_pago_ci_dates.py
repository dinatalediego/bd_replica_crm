from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["codigo_proforma", "valor"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = load_settings()
    report_path = settings.project_root / "reports" / "pago_ci_date_profile.csv"

    sql = """
        WITH ranked AS (
            SELECT
                de.codigo::text AS codigo_proforma,
                de.id,
                de.valor,
                de.fecha_actualizacion,
                row_number() OVER (
                    PARTITION BY de.codigo
                    ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
                ) AS rn
            FROM raw_cygnus.datos_extras de
            WHERE lower(de.entidad)='proforma'
              AND lower(de.nombre)='pago_ci'
        ), latest AS (
            SELECT * FROM ranked WHERE rn=1
        )
        SELECT
            codigo_proforma,
            id AS datos_extras_id,
            valor,
            fecha_actualizacion,
            analytics.try_parse_business_date(valor) AS parsed_current,
            CASE
                WHEN valor IS NULL OR btrim(valor)='' THEN 'EMPTY'
                WHEN valor ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN 'YYYY-MM-DD'
                WHEN valor ~ '^\\d{2}-\\d{2}-\\d{4}$' THEN 'DD-MM-YYYY'
                WHEN valor ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN 'DD/MM/YYYY'
                WHEN valor ~ '^\\d{4}/\\d{2}/\\d{2}$' THEN 'YYYY/MM/DD'
                WHEN valor ~ '^\\d{1,2}/\\d{1,2}/\\d{4}$' THEN 'D/M/YYYY'
                WHEN valor ~ '^\\d{4}-\\d{2}-\\d{2}[ T].*$' THEN 'TIMESTAMP_ISO_PREFIX'
                WHEN valor ~ '^\\d{2}-\\d{2}-\\d{4}[ T].*$' THEN 'TIMESTAMP_DMY_PREFIX'
                ELSE 'OTHER'
            END AS detected_pattern
        FROM latest
        WHERE valor IS NOT NULL
          AND btrim(valor)<>''
          AND analytics.try_parse_business_date(valor) IS NULL
        ORDER BY detected_pattern, valor, codigo_proforma
    """

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            names = [d.name for d in cur.description]
            rows = [dict(zip(names, row)) for row in cur.fetchall()]

        with conn.cursor() as cur:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        de.codigo,
                        de.valor,
                        row_number() OVER (
                            PARTITION BY de.codigo
                            ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
                        ) AS rn
                    FROM raw_cygnus.datos_extras de
                    WHERE lower(de.entidad)='proforma'
                      AND lower(de.nombre)='pago_ci'
                )
                SELECT
                    count(*) FILTER (WHERE rn=1 AND valor IS NOT NULL AND btrim(valor)<>'') AS latest_nonempty,
                    count(*) FILTER (
                        WHERE rn=1 AND valor IS NOT NULL AND btrim(valor)<>''
                          AND analytics.try_parse_business_date(valor) IS NULL
                    ) AS latest_unparseable,
                    count(*) FILTER (
                        WHERE valor IS NOT NULL AND btrim(valor)<>''
                          AND analytics.try_parse_business_date(valor) IS NULL
                    ) AS historical_unparseable
                FROM ranked
                """
            )
            latest_nonempty, latest_unparseable, historical_unparseable = cur.fetchone()

    _write_csv(report_path, rows)

    print("Perfil pago_ci completado")
    print(f"  latest_nonempty: {latest_nonempty}")
    print(f"  latest_unparseable: {latest_unparseable}")
    print(f"  historical_unparseable: {historical_unparseable}")
    print(f"  detalle latest no parseable: {report_path}")

    pattern_counts: dict[str, int] = {}
    for row in rows:
        pattern = str(row["detected_pattern"])
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    if pattern_counts:
        print("  patrones:")
        for pattern, count in sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"    {pattern}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
