from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def _relation_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
        return cur.fetchone()[0] is not None


def init_contract(conn, project_root: Path) -> None:
    if not _relation_exists(conn, "analytics", "int_ciclo_comercial_unidad"):
        raise RuntimeError(
            "Falta analytics.int_ciclo_comercial_unidad. Instala/refresca Absorption Phase B antes de promover el ciclo a CORE."
        )
    sql_path = project_root / "sql" / "init_core_commercial_lifecycle.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text, prepare=False)
    conn.commit()


def status(conn) -> dict[str, object]:
    if not _relation_exists(conn, "core", "v_ciclo_comercial_health"):
        raise RuntimeError("Falta core.v_ciclo_comercial_health. Ejecuta primero: python scripts/core_commercial_lifecycle.py init")

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM core.v_ciclo_comercial_health")
        row = cur.fetchone()
        keys = [desc.name for desc in cur.description]

    return dict(zip(keys, row))


def main() -> int:
    parser = argparse.ArgumentParser(description="CORE Commercial Lifecycle certified contract")
    parser.add_argument("command", choices=["init", "status"])
    args = parser.parse_args()

    settings = load_settings()
    with connect_postgres(settings) as conn:
        if args.command == "init":
            init_contract(conn, settings.project_root)
            print("CORE Commercial Lifecycle inicializado.")

        result = status(conn)

    print("CORE Commercial Lifecycle health:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    fail_keys = [
        "ciclos_duplicados",
        "unidades_no_resueltas",
        "proyectos_no_resueltos",
        "proyectos_inconsistentes",
        "resultados_no_validos",
        "abiertas_residenciales_con_pago_ci",
        "ventas_post_2026_sin_pago_ci",
        "marcadores_pago_ci_desconocidos",
    ]
    failures = {
        key: int(result[key])
        for key in fail_keys
        if key in result and result[key] is not None and int(result[key]) != 0
    }
    if failures:
        print(f"Gate CORE NO aprobado: {failures}")
        return 1

    if int(result["ciclos"]) != int(result["ciclos_distintos"]):
        print("Gate CORE NO aprobado: conteo total y granularidad distinta no coinciden.")
        return 1

    marker_debt = int(result.get("marcadores_pago_ci_confirmados_sin_fecha") or 0)
    print(
        "Gate CORE APROBADO: fecha_de_minuta gobierna la fecha de conversión; "
        "pago_ci se trata como marcador categórico. "
        f"Marcadores positivos sin fecha={marker_debt} (WARN, excluidos del risk scoring)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
