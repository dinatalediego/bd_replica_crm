"""Export a metadata-only handoff for planning Medallio ML work.

The database connection uses only POSTGRES_* settings from the local .env.
No application tables are queried, and no row values are exported.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_SCHEMAS = (
    "analytics",
    "analytics_compare",
    "analytics_market",
    "core",
    "decision_intelligence",
    "etl_control",
    "experiments",
    "features",
    "model_control",
    "observability",
    "platform_control",
    "pricing",
    "public",
    "raw_cygnus",
    "raw_mercado",
    "staging",
)

RELATIONS_SQL = """
SELECT n.nspname AS schema_name, c.relname AS object_name,
       CASE c.relkind WHEN 'r' THEN 'table'
                      WHEN 'p' THEN 'partitioned_table'
                      WHEN 'v' THEN 'view'
                      WHEN 'm' THEN 'materialized_view'
                      WHEN 'f' THEN 'foreign_table' END AS object_type,
       CASE WHEN c.relkind IN ('r', 'p', 'm') AND c.reltuples >= 0
            THEN c.reltuples::bigint END AS approximate_rows
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
ORDER BY n.nspname, c.relname
"""

COLUMNS_SQL = """
SELECT n.nspname AS schema_name, c.relname AS object_name,
       a.attnum AS ordinal_position, a.attname AS column_name,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable
FROM pg_catalog.pg_attribute AS a
JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY n.nspname, c.relname, a.attnum
"""

KEYS_SQL = """
SELECT n.nspname AS schema_name, c.relname AS object_name,
       con.conname AS constraint_name,
       CASE con.contype WHEN 'p' THEN 'primary_key'
                         WHEN 'u' THEN 'unique'
                         WHEN 'f' THEN 'foreign_key' END AS key_type,
       string_agg(a.attname, ', ' ORDER BY k.pos) AS columns,
       rn.nspname AS referenced_schema,
       rc.relname AS referenced_object,
       string_agg(ra.attname, ', ' ORDER BY k.pos)
           FILTER (WHERE con.contype = 'f') AS referenced_columns
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, pos) ON true
JOIN pg_catalog.pg_attribute AS a
  ON a.attrelid = c.oid AND a.attnum = k.attnum
LEFT JOIN pg_catalog.pg_class AS rc
  ON rc.oid = con.confrelid AND con.contype = 'f'
LEFT JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace
LEFT JOIN pg_catalog.pg_attribute AS ra
  ON ra.attrelid = rc.oid AND ra.attnum = con.confkey[k.pos::integer]
WHERE n.nspname = ANY(%s) AND con.contype IN ('p', 'u', 'f')
GROUP BY n.nspname, c.relname, con.conname, con.contype, rn.nspname, rc.relname
ORDER BY n.nspname, c.relname, con.conname
"""

FIELDS = {
    "relations.csv": ("schema_name", "object_name", "object_type", "approximate_rows"),
    "columns.csv": ("schema_name", "object_name", "ordinal_position", "column_name", "data_type", "nullable"),
    "keys.csv": ("schema_name", "object_name", "constraint_name", "key_type", "columns", "referenced_schema", "referenced_object", "referenced_columns"),
}


def fetch_metadata(conn, schemas: tuple[str, ...]) -> dict[str, list[dict]]:
    """Only query PostgreSQL catalogs in a read-only transaction."""
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '10s'")
        cur.execute("SELECT current_database() AS database_name")
        database = cur.fetchone()["database_name"]
        if database != "medallio_dw":
            raise RuntimeError(f"Base inesperada: {database}; se requiere medallio_dw")
        result = {}
        for filename, query in (
            ("relations.csv", RELATIONS_SQL),
            ("columns.csv", COLUMNS_SQL),
            ("keys.csv", KEYS_SQL),
        ):
            cur.execute(query, (list(schemas),))
            result[filename] = [dict(row) for row in cur.fetchall()]
    conn.rollback()  # Explicitly finish the read-only transaction.
    return result


def write_package(output_dir: Path, schemas: tuple[str, ...], data: dict[str, list[dict]]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    package = output_dir / f"medallio_schema_{stamp}.zip"
    if package.exists():
        raise FileExistsError(f"Ya existe: {package}")

    manifest = {
        "database": "medallio_dw",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "schemas_requested": list(schemas),
        "metadata_only": True,
        "records": {name: len(data[name]) for name in FIELDS},
        "notes": "No contiene valores de filas, muestras ni credenciales."
    }
    readme = (
        "MEDALLIO — paquete de estructura para preparar ML\n\n"
        "relations.csv: tablas/vistas y estimaciones de filas (no conteos exactos).\n"
        "columns.csv: nombres, tipos y nulabilidad; nunca valores de clientes.\n"
        "keys.csv: claves declaradas en PostgreSQL. Una unión usada por el código "
        "puede no aparecer si no tiene restricción FK.\n\n"
        "Origen: PostgreSQL local medallio_dw; no consulta Redshift. "
        "Revisa el ZIP antes de compartirlo.\n"
    )
    with ZipFile(package, "x", compression=ZIP_DEFLATED) as archive:
        for filename, fieldnames in FIELDS.items():
            # The CSV is built in memory so no duplicate loose files remain.
            import io

            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data[filename])
            archive.writestr(filename, "\ufeff" + stream.getvalue())
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("README.txt", readme)
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta solo metadatos del PostgreSQL local Medallio.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/ml_schema_handoff"),
        help="Carpeta local del ZIP (por defecto, ignorada por Git).",
    )
    parser.add_argument(
        "--schemas", nargs="+", default=DEFAULT_SCHEMAS,
        help="Esquemas a incluir; por defecto, los de la captura de Medallio.",
    )
    args = parser.parse_args()

    # Delay imports so --help and local archive checks do not need DB dependencies.
    from replica_cygnus.connections import connect_postgres
    from replica_cygnus.settings import load_settings

    settings = load_settings(require_source=False)
    if settings.postgres.host.strip().lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Este paquete solo se genera desde el PostgreSQL local (POSTGRES_HOST=localhost).")
    if settings.postgres.database != "medallio_dw":
        raise SystemExit("POSTGRES_DATABASE debe ser medallio_dw.")
    with connect_postgres(settings) as conn:
        data = fetch_metadata(conn, tuple(args.schemas))
    package = write_package(args.output_dir, tuple(args.schemas), data)
    print(f"Paquete listo: {package.resolve()}")
    print("Incluye estructura, columnas y claves. Revisa el ZIP antes de subirlo aquí.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
