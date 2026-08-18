from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _relation_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
        return cur.fetchone()[0] is not None


def main() -> int:
    settings = load_settings()
    reports = settings.project_root / "reports"

    metrics: list[dict[str, object]] = []
    duplicate_samples: list[dict[str, object]] = []

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            # -------------------------------------------------------------
            # 1) La columna id de procesos NO se asume única.
            # -------------------------------------------------------------
            cur.execute(
                """
                WITH d AS (
                    SELECT
                        id,
                        COUNT(*) AS rows_for_id,
                        COUNT(DISTINCT (
                            COALESCE(codigo_proforma::text,''),
                            COALESCE(codigo_unidad::text,''),
                            COALESCE(nombre::text,''),
                            COALESCE(fecha_inicio::text,''),
                            COALESCE(fecha_actualizacion::text,''),
                            COALESCE(estado::text,'')
                        )) AS business_signatures
                    FROM raw_cygnus.procesos
                    GROUP BY id
                    HAVING COUNT(*) > 1
                )
                SELECT
                    COUNT(*) AS duplicate_id_groups,
                    COALESCE(SUM(rows_for_id - 1),0) AS duplicate_rows_over_unique,
                    COUNT(*) FILTER (WHERE business_signatures = 1) AS same_signature_groups,
                    COUNT(*) FILTER (WHERE business_signatures > 1) AS conflicting_signature_groups
                FROM d
                """
            )
            dup_groups, dup_rows, same_sig, conflict_sig = cur.fetchone()
            metrics.extend(
                [
                    {"metric": "procesos_duplicate_id_groups", "value": int(dup_groups), "status": "WARN" if dup_groups else "PASS"},
                    {"metric": "procesos_duplicate_rows_over_unique", "value": int(dup_rows), "status": "WARN" if dup_rows else "PASS"},
                    {"metric": "procesos_same_signature_duplicate_groups", "value": int(same_sig), "status": "INFO"},
                    {"metric": "procesos_conflicting_signature_duplicate_groups", "value": int(conflict_sig), "status": "FAIL" if conflict_sig else "PASS"},
                ]
            )

            cur.execute(
                """
                WITH duplicated_ids AS (
                    SELECT id
                    FROM raw_cygnus.procesos
                    GROUP BY id
                    HAVING COUNT(*) > 1
                )
                SELECT
                    p.id,
                    p.codigo_proforma,
                    p.codigo_unidad,
                    p.codigo_proyecto,
                    p.nombre,
                    p.estado,
                    p.fecha_inicio,
                    p.fecha_fin,
                    p.fecha_anulacion,
                    p.fecha_minuta,
                    p.fecha_actualizacion,
                    p.nombre_flujo,
                    p.tipo_unidad_principal,
                    p._etl_loaded_at,
                    p._etl_source_run_id
                FROM raw_cygnus.procesos p
                JOIN duplicated_ids d USING (id)
                ORDER BY p.id, p.fecha_actualizacion NULLS LAST, p.fecha_inicio NULLS LAST
                LIMIT 500
                """
            )
            columns = [desc.name for desc in cur.description]
            for row in cur.fetchall():
                duplicate_samples.append(dict(zip(columns, row)))

            # -------------------------------------------------------------
            # 2) Candidato robusto de identidad observable del evento.
            # -------------------------------------------------------------
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        id,
                        nombre,
                        codigo_proforma,
                        codigo_unidad,
                        fecha_inicio,
                        fecha_actualizacion,
                        COUNT(*) AS n
                    FROM raw_cygnus.procesos
                    GROUP BY
                        id, nombre, codigo_proforma, codigo_unidad,
                        fecha_inicio, fecha_actualizacion
                    HAVING COUNT(*) > 1
                ) x
                """
            )
            composite_dup_groups = int(cur.fetchone()[0])
            metrics.append(
                {
                    "metric": "procesos_composite_event_duplicate_groups",
                    "value": composite_dup_groups,
                    "status": "FAIL" if composite_dup_groups else "PASS",
                }
            )

            # -------------------------------------------------------------
            # 3) Granularidad comercial: proforma + unidad.
            # -------------------------------------------------------------
            cur.execute(
                """
                WITH s AS (
                    SELECT
                        codigo_proforma,
                        codigo_unidad,
                        COUNT(*) AS separaciones
                    FROM raw_cygnus.procesos
                    WHERE nombre = 'Separacion'
                      AND fecha_inicio IS NOT NULL
                      AND COALESCE(nombre_flujo,'') <> 'Desistimiento de visita'
                    GROUP BY codigo_proforma, codigo_unidad
                )
                SELECT
                    COUNT(*) AS cycle_pairs,
                    COUNT(*) FILTER (WHERE separaciones > 1) AS pairs_with_multiple_separations,
                    COALESCE(MAX(separaciones),0) AS max_separations_per_pair
                FROM s
                """
            )
            cycle_pairs, multi_sep, max_sep = cur.fetchone()
            metrics.extend(
                [
                    {"metric": "separation_cycle_pairs", "value": int(cycle_pairs), "status": "INFO"},
                    {"metric": "pairs_with_multiple_separations", "value": int(multi_sep), "status": "WARN" if multi_sep else "PASS"},
                    {"metric": "max_separations_per_pair", "value": int(max_sep), "status": "INFO"},
                ]
            )

            cur.execute(
                """
                WITH s AS (
                    SELECT
                        codigo_proforma,
                        codigo_unidad,
                        COUNT(*) AS separaciones_activas
                    FROM raw_cygnus.procesos
                    WHERE nombre = 'Separacion'
                      AND estado = 'Activo'
                      AND fecha_inicio IS NOT NULL
                      AND COALESCE(nombre_flujo,'') <> 'Desistimiento de visita'
                    GROUP BY codigo_proforma, codigo_unidad
                )
                SELECT
                    COUNT(*) AS active_pairs,
                    COUNT(*) FILTER (WHERE separaciones_activas > 1) AS active_pairs_multiple
                FROM s
                """
            )
            active_pairs, active_multi = cur.fetchone()
            metrics.extend(
                [
                    {"metric": "active_separation_pairs", "value": int(active_pairs), "status": "INFO"},
                    {"metric": "active_pairs_with_multiple_separations", "value": int(active_multi), "status": "FAIL" if active_multi else "PASS"},
                ]
            )

            # -------------------------------------------------------------
            # 4) Proforma-unidad es histórica y puede repetir el par.
            # -------------------------------------------------------------
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT codigo_proforma, codigo_unidad
                    FROM raw_cygnus.proforma_unidad
                    GROUP BY codigo_proforma, codigo_unidad
                    HAVING COUNT(*) > 1
                ) x
                """
            )
            pu_duplicate_pairs = int(cur.fetchone()[0])
            metrics.append(
                {"metric": "proforma_unidad_duplicate_pairs", "value": pu_duplicate_pairs, "status": "INFO"}
            )

            # -------------------------------------------------------------
            # 5) Contrato existente de absorción: no duplicarlo a ciegas.
            # -------------------------------------------------------------
            lifecycle_exists = _relation_exists(conn, "analytics", "int_ciclo_comercial_unidad")
            metrics.append(
                {
                    "metric": "analytics_int_ciclo_exists",
                    "value": int(lifecycle_exists),
                    "status": "PASS" if lifecycle_exists else "WARN",
                }
            )
            if lifecycle_exists:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(DISTINCT (codigo_proforma, codigo_unidad)) AS distinct_pairs,
                        COUNT(*) - COUNT(DISTINCT (codigo_proforma, codigo_unidad)) AS duplicate_pairs
                    FROM analytics.int_ciclo_comercial_unidad
                    """
                )
                rows, distinct_pairs, duplicate_pairs = cur.fetchone()
                metrics.extend(
                    [
                        {"metric": "analytics_int_ciclo_rows", "value": int(rows), "status": "INFO"},
                        {"metric": "analytics_int_ciclo_distinct_pairs", "value": int(distinct_pairs), "status": "INFO"},
                        {"metric": "analytics_int_ciclo_duplicate_pairs", "value": int(duplicate_pairs), "status": "FAIL" if duplicate_pairs else "PASS"},
                    ]
                )

                cur.execute(
                    """
                    SELECT resultado_ciclo, COUNT(*)
                    FROM analytics.int_ciclo_comercial_unidad
                    GROUP BY resultado_ciclo
                    ORDER BY COUNT(*) DESC, resultado_ciclo
                    """
                )
                for resultado, n in cur.fetchall():
                    metrics.append(
                        {
                            "metric": f"analytics_int_ciclo_resultado::{resultado}",
                            "value": int(n),
                            "status": "INFO",
                        }
                    )

            movements_exists = _relation_exists(conn, "analytics", "fact_movimientos_stock")
            metrics.append(
                {
                    "metric": "analytics_fact_movimientos_stock_exists",
                    "value": int(movements_exists),
                    "status": "PASS" if movements_exists else "WARN",
                }
            )
            if movements_exists:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(DISTINCT movement_id) AS distinct_ids,
                        COUNT(*) - COUNT(DISTINCT movement_id) AS duplicate_ids
                    FROM analytics.fact_movimientos_stock
                    """
                )
                rows, distinct_ids, duplicate_ids = cur.fetchone()
                metrics.extend(
                    [
                        {"metric": "analytics_fact_movimientos_rows", "value": int(rows), "status": "INFO"},
                        {"metric": "analytics_fact_movimientos_duplicate_ids", "value": int(duplicate_ids), "status": "FAIL" if duplicate_ids else "PASS"},
                    ]
                )

    summary_path = reports / "commercial_lifecycle_grain_validation.csv"
    duplicates_path = reports / "commercial_lifecycle_process_duplicate_samples.csv"
    _write_csv(summary_path, ["metric", "value", "status"], metrics)

    duplicate_fields = list(duplicate_samples[0].keys()) if duplicate_samples else ["id"]
    _write_csv(duplicates_path, duplicate_fields, duplicate_samples)

    print("Commercial lifecycle grain validation completado.")
    print(f"Resumen: {summary_path}")
    print(f"Duplicados procesos: {duplicates_path}")
    print("\nMétricas:")
    for item in metrics:
        print(f"  {item['status']:<5} {item['metric']}: {item['value']}")

    failures = [m for m in metrics if m["status"] == "FAIL"]
    if failures:
        print("\nGate NO aprobado todavía: existen conflictos que deben resolverse antes de certificar el ciclo comercial en CORE.")
        return 1

    print("\nGate técnico aprobado: la granularidad candidata puede certificarse en el siguiente cambio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
