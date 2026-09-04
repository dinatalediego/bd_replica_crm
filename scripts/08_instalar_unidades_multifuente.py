from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import make_dsn

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "40_unidades_multifuente"


def _database_dsn() -> str:
    load_dotenv(ROOT / ".env", override=False)
    direct = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if direct and not (len(direct) > 2 and direct[1:3] in {":\\", ":/"}):
        return direct.strip()

    required = {
        "host": os.getenv("POSTGRES_HOST"),
        "dbname": os.getenv("POSTGRES_DATABASE"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Faltan variables PostgreSQL en .env: {', '.join(missing)}")

    return make_dsn(
        host=required["host"],
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=required["dbname"],
        user=required["user"],
        password=required["password"],
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
        connect_timeout=os.getenv("POSTGRES_CONNECT_TIMEOUT", "10"),
    )


def main() -> int:
    sql_files = sorted(SQL_DIR.glob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"No hay SQL de instalación en {SQL_DIR}")

    conn = psycopg2.connect(_database_dsn())
    try:
        with conn.cursor() as cur:
            for sql_file in sql_files:
                print(f"[RUN] {sql_file.name}")
                cur.execute(sql_file.read_text(encoding="utf-8"))

            cur.execute(
                """
                SELECT esquema_fuente, count(*)
                FROM core.v_unidades_fuentes
                GROUP BY esquema_fuente
                ORDER BY esquema_fuente
                """
            )
            counts = cur.fetchall()

            cur.execute(
                """
                SELECT
                    (SELECT count(*) FROM analytics_market.v_unidad_lifecycle_inferido),
                    (SELECT count(*) FROM analytics_market.v_movimientos_inventario_inferidos),
                    (SELECT count(*) FROM analytics_compare.v_powerbi_proyecto_actual),
                    (SELECT count(*) FROM core.v_unidad_comercial_multifuente),
                    (SELECT count(*) FROM analytics_compare.v_powerbi_unidad_actual),
                    (SELECT count(*) FROM analytics_compare.v_powerbi_unidad_actual WHERE esquema_fuente = 'raw_mercado'),
                    (SELECT count(*) FROM analytics_compare.v_powerbi_unidad_actual WHERE esquema_fuente = 'raw_mercado' AND tipologia_ubicacion IS NOT NULL)
                """
            )
            (
                mercado_unidades,
                mercado_movimientos,
                proyectos_powerbi,
                unidades_comercial,
                unidades_powerbi,
                unidades_mercado_powerbi,
                mercado_con_tipologia_ubicacion,
            ) = cur.fetchone()

            total_fuentes = sum(int(filas) for _, filas in counts)
            if int(unidades_comercial) != total_fuentes:
                raise RuntimeError(
                    f"Reconciliación multifuente fallida: fuentes={total_fuentes}, comercial={unidades_comercial}"
                )
            if int(unidades_powerbi) != int(unidades_comercial):
                raise RuntimeError(
                    f"Reconciliación Power BI fallida: comercial={unidades_comercial}, powerbi={unidades_powerbi}"
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[OK] capa multifuente + comercial + analítica comparativa creada/actualizada")
    for fuente, filas in counts:
        print(f"  core.v_unidades_fuentes {fuente}: {filas}")
    print(f"  core.v_unidad_comercial_multifuente total: {unidades_comercial}")
    print(f"  analytics_compare unidades Power BI: {unidades_powerbi}")
    print(f"  analytics_compare raw_mercado Power BI: {unidades_mercado_powerbi}")
    print(f"  raw_mercado con tipologia_ubicacion: {mercado_con_tipologia_ubicacion}")
    print(f"  analytics_market lifecycle unidades: {mercado_unidades}")
    print(f"  analytics_market movimientos inferidos: {mercado_movimientos}")
    print(f"  analytics_compare proyectos Power BI: {proyectos_powerbi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
