from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main() -> int:
    settings = load_settings()
    sql_path = Path(settings.project_root) / "sql" / "init_unidades_powerbi.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    with connect_postgres(settings) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_text, prepare=False)
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE fuente_esquema = 'raw_cygnus') AS cygnus,
                    COUNT(*) FILTER (WHERE fuente_esquema = 'raw_mercado') AS mercado,
                    COUNT(*) FILTER (WHERE estado = 'Sin clasificar') AS sin_clasificar,
                    COUNT(*) FILTER (
                        WHERE tipologia_ubicacion IS DISTINCT FROM RIGHT(codigo, 2)
                    ) AS tipologia_inconsistente
                FROM analytics.unidades_powerbi
                """
            )
            total, cygnus, mercado, sin_clasificar, tipologia_inconsistente = cursor.fetchone()
        conn.commit()

    print("analytics.unidades_powerbi actualizado:")
    print(f"  total: {total}")
    print(f"  raw_cygnus: {cygnus}")
    print(f"  raw_mercado: {mercado}")
    print(f"  sin_clasificar: {sin_clasificar}")
    print(f"  tipologia_inconsistente: {tipologia_inconsistente}")

    if tipologia_inconsistente:
        raise RuntimeError(
            f"tipologia_ubicacion inconsistente en {tipologia_inconsistente} filas"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
