from __future__ import annotations

import csv
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

TABLES = [
    "clientes",
    "clientes_proyectos",
    "proformas",
    "proforma_unidad",
    "procesos",
    "unidades",
]

VALUE_PROFILE_CANDIDATES = {
    "procesos": ["nombre", "estado", "tipo_unidad_principal", "nombre_proyecto"],
    "proformas": ["estado", "codigo_proforma", "codigo_proyecto"],
    "proforma_unidad": ["estado", "codigo_proforma", "codigo_unidad"],
    "unidades": ["estado_comercial", "tipo_unidad", "codigo_proyecto"],
}


def _relation_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{table}",))
        return cur.fetchone()[0] is not None


def _columns(conn, schema: str, table: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ordinal_position, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return list(cur.fetchall())


def _column_names(conn, schema: str, table: str) -> set[str]:
    return {row[1] for row in _columns(conn, schema, table)}


def _table_profile(conn, schema: str, table: str, columns: set[str]) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        rows = int(cur.fetchone()[0])

        distinct_id = None
        duplicate_ids = None
        null_ids = None
        if "id" in columns:
            cur.execute(
                f'SELECT COUNT(DISTINCT id), COUNT(*) - COUNT(DISTINCT id), COUNT(*) FILTER (WHERE id IS NULL) '
                f'FROM "{schema}"."{table}"'
            )
            distinct_id, duplicate_ids, null_ids = cur.fetchone()

    return {
        "table": table,
        "rows": rows,
        "distinct_id": distinct_id,
        "duplicate_ids": duplicate_ids,
        "null_ids": null_ids,
    }


def _value_profiles(conn, schema: str, table: str, columns: set[str]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for column in VALUE_PROFILE_CANDIDATES.get(table, []):
        if column not in columns:
            continue
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT COALESCE(CAST("{column}" AS text), \'<NULL>\') AS value, COUNT(*) AS rows '
                f'FROM "{schema}"."{table}" '
                f'GROUP BY 1 ORDER BY rows DESC, value LIMIT 50'
            )
            for value, rows in cur.fetchall():
                results.append(
                    {
                        "table": table,
                        "column": column,
                        "value": value,
                        "rows": int(rows),
                    }
                )
    return results


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    settings = load_settings()
    reports = settings.project_root / "reports"
    schema = "raw_cygnus"

    column_rows: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []
    value_rows: list[dict[str, object]] = []

    with connect_postgres(settings) as conn:
        for table in TABLES:
            if not _relation_exists(conn, schema, table):
                table_rows.append(
                    {
                        "table": table,
                        "rows": None,
                        "distinct_id": None,
                        "duplicate_ids": None,
                        "null_ids": None,
                    }
                )
                continue

            cols = _columns(conn, schema, table)
            col_names = {row[1] for row in cols}
            for ordinal, name, data_type in cols:
                column_rows.append(
                    {
                        "table": table,
                        "ordinal_position": ordinal,
                        "column_name": name,
                        "data_type": data_type,
                    }
                )

            table_rows.append(_table_profile(conn, schema, table, col_names))
            value_rows.extend(_value_profiles(conn, schema, table, col_names))

    columns_path = reports / "commercial_lifecycle_columns.csv"
    tables_path = reports / "commercial_lifecycle_table_profile.csv"
    values_path = reports / "commercial_lifecycle_value_profile.csv"

    _write_csv(
        columns_path,
        ["table", "ordinal_position", "column_name", "data_type"],
        column_rows,
    )
    _write_csv(
        tables_path,
        ["table", "rows", "distinct_id", "duplicate_ids", "null_ids"],
        table_rows,
    )
    _write_csv(
        values_path,
        ["table", "column", "value", "rows"],
        value_rows,
    )

    print("Commercial lifecycle discovery completado.")
    print(f"Columnas: {columns_path}")
    print(f"Perfil tablas: {tables_path}")
    print(f"Perfil valores: {values_path}")
    print("\nResumen:")
    for row in table_rows:
        print(
            f"  {row['table']}: rows={row['rows']} "
            f"distinct_id={row['distinct_id']} duplicate_ids={row['duplicate_ids']} null_ids={row['null_ids']}"
        )
    print("\nSiguiente gate: fijar la granularidad y reglas de eventos antes de crear fact_ciclo_comercial_unidad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
