from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _relation_exists(conn, schema: str, relation: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{relation}",))
        return cur.fetchone()[0] is not None


def _missing_pairs(conn) -> list[dict[str, object]]:
    exclusions_exists = _relation_exists(conn, "etl_control", "business_exclusions")
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

    sql = f"""
        WITH expected AS (
            SELECT DISTINCT ON (p.codigo_proforma, p.codigo_unidad)
                p.codigo_proforma::text AS codigo_proforma,
                p.codigo_unidad::text AS codigo_unidad,
                p.codigo_proyecto::text AS codigo_proyecto,
                p.id AS separacion_source_id,
                p.estado::text AS estado_separacion,
                p.fecha_inicio,
                p.fecha_actualizacion,
                p.tipo_unidad_principal::text AS tipo_unidad_principal,
                p.nombre_flujo::text AS nombre_flujo
            FROM raw_cygnus.procesos p
            WHERE p.nombre = 'Separacion'
              AND p.fecha_inicio IS NOT NULL
              AND COALESCE(p.nombre_flujo,'') <> 'Desistimiento de visita'
              {exclusion_clause}
            ORDER BY p.codigo_proforma, p.codigo_unidad, p.fecha_inicio, p.id
        )
        SELECT
            e.codigo_proforma,
            e.codigo_unidad,
            e.codigo_proyecto,
            e.separacion_source_id,
            e.estado_separacion,
            e.fecha_inicio,
            e.fecha_actualizacion,
            e.tipo_unidad_principal,
            e.nombre_flujo
        FROM expected e
        LEFT JOIN analytics.int_ciclo_comercial_unidad a
          USING (codigo_proforma, codigo_unidad)
        WHERE a.codigo_proforma IS NULL
        ORDER BY e.fecha_inicio, e.codigo_proforma, e.codigo_unidad
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        names = [desc.name for desc in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def _counts(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM analytics.int_ciclo_comercial_unidad")
        lifecycle_rows = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM analytics.fact_movimientos_stock")
        movement_rows = int(cur.fetchone()[0])
    return lifecycle_rows, movement_rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else ["codigo_proforma"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = load_settings()
    reports = settings.project_root / "reports"
    before_path = reports / "commercial_lifecycle_missing_pairs_before_refresh.csv"
    after_path = reports / "commercial_lifecycle_missing_pairs_after_refresh.csv"

    with connect_postgres(settings) as conn:
        if not _relation_exists(conn, "analytics", "int_ciclo_comercial_unidad"):
            raise RuntimeError("Falta analytics.int_ciclo_comercial_unidad. Instala Fase B antes de reconciliar.")
        if not _relation_exists(conn, "analytics", "fact_movimientos_stock"):
            raise RuntimeError("Falta analytics.fact_movimientos_stock. Instala Fase B antes de reconciliar.")

        missing_before = _missing_pairs(conn)
        lifecycle_before, movements_before = _counts(conn)
        _write_csv(before_path, missing_before)

        print("Reconciliación commercial lifecycle")
        print(f"  ciclos antes: {lifecycle_before}")
        print(f"  movimientos antes: {movements_before}")
        print(f"  pares esperados faltantes antes: {len(missing_before)}")
        print(f"  detalle antes: {before_path}")

        with conn.cursor() as cur:
            cur.execute("CALL analytics.refresh_absorption_phase_b_full()")
        conn.commit()

        missing_after = _missing_pairs(conn)
        lifecycle_after, movements_after = _counts(conn)
        _write_csv(after_path, missing_after)

        print("\nDespués del refresh Fase B")
        print(f"  ciclos después: {lifecycle_after}")
        print(f"  movimientos después: {movements_after}")
        print(f"  pares esperados faltantes después: {len(missing_after)}")
        print(f"  detalle después: {after_path}")

        if missing_after:
            print("\nGate NO aprobado: persisten pares RAW esperados ausentes en analytics.")
            return 1

    print("\nGate de reconciliación aprobado: RAW esperado y analytics.int_ciclo_comercial_unidad están alineados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
