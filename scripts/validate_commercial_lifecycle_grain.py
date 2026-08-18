from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


LIFECYCLE_EVENTS = ("Separacion", "Venta", "Anulacion")


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


def _add(metrics: list[dict[str, object]], metric: str, value: int, status: str) -> None:
    metrics.append({"metric": metric, "value": int(value), "status": status})


def main() -> int:
    settings = load_settings()
    reports = settings.project_root / "reports"

    metrics: list[dict[str, object]] = []
    duplicate_samples: list[dict[str, object]] = []
    collision_profile: list[dict[str, object]] = []

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            # -------------------------------------------------------------
            # 1) raw_cygnus.procesos.id NO es globalmente único.
            #    La validación distingue colisiones entre namespaces/flujos
            #    de colisiones peligrosas dentro de los eventos del ciclo.
            # -------------------------------------------------------------
            cur.execute(
                """
                WITH duplicated AS (
                    SELECT id
                    FROM raw_cygnus.procesos
                    GROUP BY id
                    HAVING COUNT(*) > 1
                ), classified AS (
                    SELECT
                        p.id,
                        COUNT(*) AS rows_for_id,
                        COUNT(*) FILTER (
                            WHERE p.nombre IN ('Separacion','Venta','Anulacion')
                        ) AS lifecycle_rows,
                        COUNT(*) FILTER (WHERE p.nombre = 'Entrega') AS entrega_rows,
                        COUNT(DISTINCT p.nombre) AS distinct_process_names
                    FROM raw_cygnus.procesos p
                    JOIN duplicated d USING (id)
                    GROUP BY p.id
                )
                SELECT
                    COUNT(*) AS duplicate_id_groups,
                    COALESCE(SUM(rows_for_id - 1),0) AS duplicate_rows_over_unique,
                    COUNT(*) FILTER (WHERE entrega_rows > 0) AS groups_with_entrega,
                    COUNT(*) FILTER (WHERE lifecycle_rows > 1) AS unsafe_lifecycle_id_groups,
                    COUNT(*) FILTER (
                        WHERE lifecycle_rows = 1
                          AND entrega_rows >= 1
                    ) AS safe_cross_namespace_groups
                FROM classified
                """
            )
            dup_groups, dup_rows, with_entrega, unsafe_lifecycle_ids, safe_cross_namespace = cur.fetchone()
            _add(metrics, "procesos_duplicate_id_groups", dup_groups, "WARN" if dup_groups else "PASS")
            _add(metrics, "procesos_duplicate_rows_over_unique", dup_rows, "WARN" if dup_rows else "PASS")
            _add(metrics, "procesos_duplicate_id_groups_with_entrega", with_entrega, "INFO")
            _add(
                metrics,
                "procesos_safe_cross_namespace_id_groups",
                safe_cross_namespace,
                "INFO",
            )
            _add(
                metrics,
                "procesos_unsafe_lifecycle_id_groups",
                unsafe_lifecycle_ids,
                "FAIL" if unsafe_lifecycle_ids else "PASS",
            )

            # Perfil completo de combinaciones de procesos que comparten id.
            cur.execute(
                """
                WITH duplicated AS (
                    SELECT id
                    FROM raw_cygnus.procesos
                    GROUP BY id
                    HAVING COUNT(*) > 1
                ), names AS (
                    SELECT p.id, string_agg(p.nombre, ' + ' ORDER BY p.nombre) AS process_names
                    FROM raw_cygnus.procesos p
                    JOIN duplicated d USING (id)
                    GROUP BY p.id
                )
                SELECT process_names, COUNT(*) AS id_groups
                FROM names
                GROUP BY process_names
                ORDER BY id_groups DESC, process_names
                """
            )
            for process_names, id_groups in cur.fetchall():
                collision_profile.append(
                    {"process_names": process_names, "id_groups": int(id_groups)}
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
            # 2) Contrato de identidad de evento.
            #    Nunca usar procesos.id solo como identidad global.
            #    Para el ciclo comercial, (nombre, id) / source_event_key
            #    debe ser único dentro de Separacion/Venta/Anulacion.
            # -------------------------------------------------------------
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT nombre, id
                    FROM raw_cygnus.procesos
                    WHERE nombre IN ('Separacion','Venta','Anulacion')
                    GROUP BY nombre, id
                    HAVING COUNT(*) > 1
                ) x
                """
            )
            lifecycle_event_key_dups = int(cur.fetchone()[0])
            _add(
                metrics,
                "lifecycle_event_key_duplicate_groups",
                lifecycle_event_key_dups,
                "FAIL" if lifecycle_event_key_dups else "PASS",
            )

            # Firma observable más fuerte para detectar duplicados exactos.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT
                        nombre,
                        id,
                        codigo_proforma,
                        codigo_unidad,
                        fecha_inicio,
                        fecha_actualizacion,
                        COUNT(*) AS n
                    FROM raw_cygnus.procesos
                    WHERE nombre IN ('Separacion','Venta','Anulacion')
                    GROUP BY
                        nombre, id, codigo_proforma, codigo_unidad,
                        fecha_inicio, fecha_actualizacion
                    HAVING COUNT(*) > 1
                ) x
                """
            )
            lifecycle_signature_dups = int(cur.fetchone()[0])
            _add(
                metrics,
                "lifecycle_event_signature_duplicate_groups",
                lifecycle_signature_dups,
                "FAIL" if lifecycle_signature_dups else "PASS",
            )

            # -------------------------------------------------------------
            # 3) Granularidad comercial: un ciclo por proforma + unidad.
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
            _add(metrics, "separation_cycle_pairs", cycle_pairs, "INFO")
            _add(metrics, "pairs_with_multiple_separations", multi_sep, "FAIL" if multi_sep else "PASS")
            _add(metrics, "max_separations_per_pair", max_sep, "INFO")

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
            _add(metrics, "active_separation_pairs", active_pairs, "INFO")
            _add(
                metrics,
                "active_pairs_with_multiple_separations",
                active_multi,
                "FAIL" if active_multi else "PASS",
            )

            # -------------------------------------------------------------
            # 4) Reconciliación exacta RAW esperado -> analytics ciclo.
            #    Las exclusiones de negocio activas son parte del contrato.
            # -------------------------------------------------------------
            lifecycle_exists = _relation_exists(conn, "analytics", "int_ciclo_comercial_unidad")
            exclusions_exists = _relation_exists(conn, "etl_control", "business_exclusions")
            _add(metrics, "analytics_int_ciclo_exists", int(lifecycle_exists), "PASS" if lifecycle_exists else "FAIL")
            _add(metrics, "business_exclusions_exists", int(exclusions_exists), "PASS" if exclusions_exists else "WARN")

            if lifecycle_exists:
                exclusion_clause = """
                    AND NOT EXISTS (
                        SELECT 1
                        FROM etl_control.business_exclusions e
                        WHERE e.entity_type = 'PROFORMA'
                          AND e.entity_key = p.codigo_proforma::text
                          AND e.scope = 'COMMERCIAL_ANALYTICS'
                          AND e.is_active
                    )
                """ if exclusions_exists else ""

                reconciliation_sql = f"""
                    WITH expected AS (
                        SELECT DISTINCT
                            p.codigo_proforma::text AS codigo_proforma,
                            p.codigo_unidad::text AS codigo_unidad
                        FROM raw_cygnus.procesos p
                        WHERE p.nombre = 'Separacion'
                          AND p.fecha_inicio IS NOT NULL
                          AND COALESCE(p.nombre_flujo,'') <> 'Desistimiento de visita'
                          {exclusion_clause}
                    ), actual AS (
                        SELECT codigo_proforma::text, codigo_unidad::text
                        FROM analytics.int_ciclo_comercial_unidad
                    )
                    SELECT
                        (SELECT COUNT(*) FROM expected) AS expected_pairs,
                        (SELECT COUNT(*) FROM actual) AS actual_pairs,
                        (
                            SELECT COUNT(*)
                            FROM expected e
                            LEFT JOIN actual a USING (codigo_proforma, codigo_unidad)
                            WHERE a.codigo_proforma IS NULL
                        ) AS missing_pairs,
                        (
                            SELECT COUNT(*)
                            FROM actual a
                            LEFT JOIN expected e USING (codigo_proforma, codigo_unidad)
                            WHERE e.codigo_proforma IS NULL
                        ) AS unexpected_pairs
                """
                cur.execute(reconciliation_sql)
                expected_pairs, actual_pairs, missing_pairs, unexpected_pairs = cur.fetchone()
                _add(metrics, "analytics_int_ciclo_expected_pairs", expected_pairs, "INFO")
                _add(metrics, "analytics_int_ciclo_rows", actual_pairs, "INFO")
                _add(
                    metrics,
                    "analytics_int_ciclo_missing_expected_pairs",
                    missing_pairs,
                    "FAIL" if missing_pairs else "PASS",
                )
                _add(
                    metrics,
                    "analytics_int_ciclo_unexpected_pairs",
                    unexpected_pairs,
                    "FAIL" if unexpected_pairs else "PASS",
                )

                cur.execute(
                    """
                    SELECT
                        COUNT(*) - COUNT(DISTINCT (codigo_proforma, codigo_unidad)) AS duplicate_pairs
                    FROM analytics.int_ciclo_comercial_unidad
                    """
                )
                duplicate_pairs = int(cur.fetchone()[0])
                _add(
                    metrics,
                    "analytics_int_ciclo_duplicate_pairs",
                    duplicate_pairs,
                    "FAIL" if duplicate_pairs else "PASS",
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
                    _add(metrics, f"analytics_int_ciclo_resultado::{resultado}", n, "INFO")

            # proforma_unidad es histórica: repetir el par no invalida el ciclo.
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
            _add(metrics, "proforma_unidad_duplicate_pairs", pu_duplicate_pairs, "INFO")

            movements_exists = _relation_exists(conn, "analytics", "fact_movimientos_stock")
            _add(
                metrics,
                "analytics_fact_movimientos_stock_exists",
                int(movements_exists),
                "PASS" if movements_exists else "FAIL",
            )
            if movements_exists:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS rows,
                        COUNT(*) - COUNT(DISTINCT movement_id) AS duplicate_ids,
                        COUNT(*) - COUNT(DISTINCT source_event_key) AS duplicate_source_event_keys
                    FROM analytics.fact_movimientos_stock
                    """
                )
                rows, duplicate_ids, duplicate_source_keys = cur.fetchone()
                _add(metrics, "analytics_fact_movimientos_rows", rows, "INFO")
                _add(
                    metrics,
                    "analytics_fact_movimientos_duplicate_ids",
                    duplicate_ids,
                    "FAIL" if duplicate_ids else "PASS",
                )
                _add(
                    metrics,
                    "analytics_fact_movimientos_duplicate_source_event_keys",
                    duplicate_source_keys,
                    "FAIL" if duplicate_source_keys else "PASS",
                )

    summary_path = reports / "commercial_lifecycle_grain_validation.csv"
    duplicates_path = reports / "commercial_lifecycle_process_duplicate_samples.csv"
    collisions_path = reports / "commercial_lifecycle_id_collision_profile.csv"
    _write_csv(summary_path, ["metric", "value", "status"], metrics)

    duplicate_fields = list(duplicate_samples[0].keys()) if duplicate_samples else ["id"]
    _write_csv(duplicates_path, duplicate_fields, duplicate_samples)
    _write_csv(collisions_path, ["process_names", "id_groups"], collision_profile)

    print("Commercial lifecycle grain validation completado.")
    print(f"Resumen: {summary_path}")
    print(f"Duplicados procesos: {duplicates_path}")
    print(f"Perfil colisiones ID: {collisions_path}")
    print("\nMétricas:")
    for item in metrics:
        print(f"  {item['status']:<5} {item['metric']}: {item['value']}")

    failures = [m for m in metrics if m["status"] == "FAIL"]
    if failures:
        print("\nGate NO aprobado: queda al menos una colisión o reconciliación insegura para el ciclo comercial.")
        return 1

    print("\nGate técnico APROBADO: procesos.id no es globalmente único, pero la identidad de eventos del ciclo y la reconciliación RAW -> analytics son seguras.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
