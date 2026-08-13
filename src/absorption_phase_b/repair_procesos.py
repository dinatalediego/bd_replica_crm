"""
Reparación one-time de raw_cygnus.procesos.

Motivo:
Redshift contiene IDs repetidos entre distintos `nombre`.
El source key validado es (nombre,id).

La operación es transaccional en PostgreSQL.
No escribe en Redshift.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
from collections import Counter

import psycopg
from psycopg import sql
import redshift_connector

ROOT = Path(__file__).resolve().parents[2]

def load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def pg_conn():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE", "medallio_dw"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
    )

def rs_conn():
    kwargs = dict(
        host=os.environ["REDSHIFT_HOST"],
        port=int(os.getenv("REDSHIFT_PORT", "5439")),
        database=os.environ["REDSHIFT_DATABASE"],
        user=os.environ["REDSHIFT_USER"],
        password=os.environ["REDSHIFT_PASSWORD"],
    )
    # Respetar SSL si está configurado.
    ssl = os.getenv("REDSHIFT_SSL", "true").lower() in ("1","true","yes","y")
    kwargs["ssl"] = ssl
    return redshift_connector.connect(**kwargs)

def main():
    load_env()

    with rs_conn() as rs:
        cur = rs.cursor()
        cur.execute("SELECT * FROM grupocygnus.procesos ORDER BY nombre, id")
        rows = cur.fetchall()
        src_cols = [d[0] for d in cur.description]

    print(f"Redshift filas: {len(rows):,}")

    idx_id = src_cols.index("id")
    idx_nombre = src_cols.index("nombre")

    composite = [(r[idx_nombre], r[idx_id]) for r in rows]
    dup_composite = [k for k, n in Counter(composite).items() if n > 1]
    if dup_composite:
        raise RuntimeError(
            f"(nombre,id) NO es único. Ejemplos: {dup_composite[:10]}"
        )

    id_counts = Counter(r[idx_id] for r in rows)
    repeated_ids = sum(1 for n in id_counts.values() if n > 1)
    print(f"IDs globales repetidos: {repeated_ids:,}")
    print(f"(nombre,id) distintos: {len(set(composite)):,}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"procesos_backup_keyfix_{stamp}"

    with pg_conn() as pg:
        with pg.transaction():
            db = pg.execute("SELECT current_database()").fetchone()[0]
            if db != os.getenv("POSTGRES_DATABASE", "medallio_dw"):
                raise RuntimeError(f"Base inesperada: {db}")

            # Target columns reales.
            target_cols = [
                r[0] for r in pg.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='raw_cygnus'
                      AND table_name='procesos'
                    ORDER BY ordinal_position
                """).fetchall()
            ]
            if not target_cols:
                raise RuntimeError("No existe raw_cygnus.procesos")

            insert_cols = [c for c in src_cols if c in target_cols]
            missing_required = {"id","nombre"} - set(insert_cols)
            if missing_required:
                raise RuntimeError(f"Faltan columnas requeridas: {missing_required}")

            # Backup de datos actuales.
            pg.execute(
                sql.SQL("CREATE TABLE raw_cygnus.{} AS TABLE raw_cygnus.procesos")
                .format(sql.Identifier(backup_name))
            )
            print(f"Backup creado: raw_cygnus.{backup_name}")

            # Eliminar constraints unique/PK que sean EXCLUSIVAMENTE sobre id.
            constraints = pg.execute("""
                SELECT con.conname,
                       con.contype,
                       array_agg(att.attname ORDER BY u.ord) AS cols
                FROM pg_constraint con
                JOIN LATERAL unnest(con.conkey) WITH ORDINALITY u(attnum, ord) ON true
                JOIN pg_attribute att
                  ON att.attrelid = con.conrelid
                 AND att.attnum = u.attnum
                WHERE con.conrelid = 'raw_cygnus.procesos'::regclass
                  AND con.contype IN ('p','u')
                GROUP BY con.conname, con.contype
            """).fetchall()

            for conname, contype, cols in constraints:
                if list(cols) == ["id"]:
                    pg.execute(
                        sql.SQL("ALTER TABLE raw_cygnus.procesos DROP CONSTRAINT {}")
                        .format(sql.Identifier(conname))
                    )
                    print(f"Constraint removida por colisión global id: {conname}")

            # Eliminar unique indexes no asociados a constraint, solo sobre id.
            indexes = pg.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname='raw_cygnus'
                  AND tablename='procesos'
            """).fetchall()
            for indexname, indexdef in indexes:
                normalized = " ".join(indexdef.lower().split())
                if " unique index " in f" {normalized} " and normalized.endswith("(id)"):
                    # Si ya desapareció por DROP CONSTRAINT, DROP IF EXISTS es seguro.
                    pg.execute(
                        sql.SQL("DROP INDEX IF EXISTS raw_cygnus.{}")
                        .format(sql.Identifier(indexname))
                    )

            pg.execute("TRUNCATE TABLE raw_cygnus.procesos")

            placeholders = sql.SQL(",").join(sql.Placeholder() for _ in insert_cols)
            insert_stmt = sql.SQL("INSERT INTO raw_cygnus.procesos ({}) VALUES ({})").format(
                sql.SQL(",").join(map(sql.Identifier, insert_cols)),
                placeholders,
            )

            src_positions = [src_cols.index(c) for c in insert_cols]
            data = [tuple(r[i] for i in src_positions) for r in rows]

            # 5k filas: executemany es suficientemente seguro y simple.
            with pg.cursor() as c:
                c.executemany(insert_stmt, data)

            # Completar metadata local si existen.
            if "_etl_loaded_at" in target_cols:
                pg.execute("""
                    UPDATE raw_cygnus.procesos
                    SET _etl_loaded_at = COALESCE(_etl_loaded_at, now())
                """)

            pg.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_cygnus_procesos_nombre_id
                ON raw_cygnus.procesos(nombre, id)
            """)

            row = pg.execute("""
                SELECT
                    count(*) AS filas,
                    count(DISTINCT (nombre,id)) AS composite_distinct
                FROM raw_cygnus.procesos
            """).fetchone()

            if row[0] != len(rows) or row[1] != len(rows):
                raise RuntimeError(
                    f"Reconciliación falló: local={row}, source={len(rows)}"
                )

        print("COMMIT OK")
        print(f"PostgreSQL filas: {len(rows):,}")
        print("Source key: (nombre,id)")

if __name__ == "__main__":
    main()
