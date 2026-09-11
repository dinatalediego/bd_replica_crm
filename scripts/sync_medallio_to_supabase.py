from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg import sql
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "supabase_medallio_replica.yml"


@dataclass(frozen=True)
class ColumnDef:
    name: str
    source_type: str
    target_type: str


@dataclass(frozen=True)
class Relation:
    schema: str
    name: str
    object_type: str


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def relation_id(schema: str, relation: str) -> str:
    return f"{schema}.{relation}"


def discover_relations(conn: psycopg.Connection, schemas: Iterable[str]) -> list[Relation]:
    schemas = list(schemas)
    query = """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = ANY(%s)
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
    """
    with conn.cursor() as cur:
        cur.execute(query, (schemas,))
        return [Relation(*row) for row in cur.fetchall()]


def discover_columns(conn: psycopg.Connection, relation: Relation) -> list[ColumnDef]:
    query = """
        SELECT
            a.attname,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type,
            tn.nspname AS type_schema,
            t.typtype
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
        JOIN pg_catalog.pg_namespace tn ON tn.oid = t.typnamespace
        WHERE n.nspname = %s
          AND c.relname = %s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
    """
    out: list[ColumnDef] = []
    with conn.cursor() as cur:
        cur.execute(query, (relation.schema, relation.name))
        for name, formatted_type, type_schema, typtype in cur.fetchall():
            target_type = formatted_type
            # Research replica prioritizes preserving values. Custom enum/domain
            # types may not exist in Supabase, so store those as text.
            if type_schema != "pg_catalog" and typtype in {"e", "d"}:
                target_type = "text"
            out.append(ColumnDef(name=name, source_type=formatted_type, target_type=target_type))
    return out


def signature(columns: list[ColumnDef]) -> str:
    payload = json.dumps(
        [(c.name, c.source_type, c.target_type) for c in columns],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def qident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def ensure_target_schema_exists(conn: psycopg.Connection, schema_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regnamespace(%s)", (schema_name,))
        if cur.fetchone()[0] is None:
            raise RuntimeError(
                f"Target schema {schema_name!r} no existe. "
                "Aplica primero sql/90_supabase_research_replica/00_private_zone.sql."
            )


def ensure_target_table(
    conn: psycopg.Connection,
    source_relation: Relation,
    target_schema: str,
    columns: list[ColumnDef],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
                  AND table_type = 'BASE TABLE'
            )
            """,
            (target_schema, source_relation.name),
        )
        exists = bool(cur.fetchone()[0])

    if exists:
        return

    col_defs = [
        sql.SQL("{} {}").format(qident(c.name), sql.SQL(c.target_type))
        for c in columns
    ]
    create_stmt = sql.SQL("CREATE TABLE {}.{} ({})").format(
        qident(target_schema),
        qident(source_relation.name),
        sql.SQL(", ").join(col_defs),
    )
    with conn.cursor() as cur:
        cur.execute(create_stmt)
        cur.execute(
            sql.SQL("COMMENT ON TABLE {}.{} IS %s").format(
                qident(target_schema), qident(source_relation.name)
            ),
            (
                f"Private research replica of "
                f"{source_relation.schema}.{source_relation.name} from medallio_dw.",
            ),
        )


def table_count(conn: psycopg.Connection, schema_name: str, table_name: str) -> int:
    stmt = sql.SQL("SELECT count(*) FROM {}.{}").format(
        qident(schema_name), qident(table_name)
    )
    with conn.cursor() as cur:
        cur.execute(stmt)
        return int(cur.fetchone()[0])


def copy_table(
    source: psycopg.Connection,
    target: psycopg.Connection,
    relation: Relation,
    target_schema: str,
    columns: list[ColumnDef],
) -> None:
    column_names = [c.name for c in columns]
    col_sql = sql.SQL(", ").join(qident(c) for c in column_names)

    source_stmt = sql.SQL(
        "COPY (SELECT {} FROM {}.{}) TO STDOUT "
        "WITH (FORMAT CSV, NULL '\\N')"
    ).format(col_sql, qident(relation.schema), qident(relation.name))

    target_stmt = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN "
        "WITH (FORMAT CSV, NULL '\\N')"
    ).format(qident(target_schema), qident(relation.name), col_sql)

    with source.cursor() as src_cur, target.cursor() as dst_cur:
        with src_cur.copy(source_stmt) as copy_out, dst_cur.copy(target_stmt) as copy_in:
            while True:
                block = copy_out.read()
                if not block:
                    break
                copy_in.write(block)


def create_sync_run(
    conn: psycopg.Connection,
    schemas: list[str],
    tables_discovered: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO medallio_admin.sync_runs
                (sync_mode, schemas_requested, tables_discovered, metadata)
            VALUES
                ('initial_snapshot', %s, %s, %s::jsonb)
            RETURNING sync_run_id
            """,
            (
                schemas,
                tables_discovered,
                json.dumps({"writer": "scripts/sync_medallio_to_supabase.py"}),
            ),
        )
        return int(cur.fetchone()[0])


def start_table_event(
    conn: psycopg.Connection,
    sync_run_id: int,
    relation: Relation,
    target_schema: str,
    source_rows: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO medallio_admin.sync_table_events (
                sync_run_id, source_schema, source_relation,
                target_schema, target_relation, source_rows, status
            )
            VALUES (%s,%s,%s,%s,%s,%s,'running')
            ON CONFLICT (sync_run_id, source_schema, source_relation)
            DO UPDATE SET
                started_at = now(),
                finished_at = NULL,
                source_rows = EXCLUDED.source_rows,
                target_rows = NULL,
                status = 'running',
                error_message = NULL
            """,
            (
                sync_run_id,
                relation.schema,
                relation.name,
                target_schema,
                relation.name,
                source_rows,
            ),
        )


def finish_table_event(
    conn: psycopg.Connection,
    sync_run_id: int,
    relation: Relation,
    target_schema: str,
    columns: list[ColumnDef],
    source_rows: int,
    target_rows: int,
    status: str,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE medallio_admin.sync_table_events
               SET finished_at = now(),
                   target_rows = %s,
                   status = %s,
                   error_message = %s
             WHERE sync_run_id = %s
               AND source_schema = %s
               AND source_relation = %s
            """,
            (
                target_rows,
                status,
                error_message,
                sync_run_id,
                relation.schema,
                relation.name,
            ),
        )
        cur.execute(
            """
            INSERT INTO medallio_admin.table_registry (
                source_schema, source_relation, source_object_type,
                target_schema, target_relation, column_signature,
                source_rows, target_rows, last_sync_run_id,
                last_synced_at, sync_status, notes
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s)
            ON CONFLICT (source_schema, source_relation)
            DO UPDATE SET
                source_object_type = EXCLUDED.source_object_type,
                target_schema = EXCLUDED.target_schema,
                target_relation = EXCLUDED.target_relation,
                column_signature = EXCLUDED.column_signature,
                source_rows = EXCLUDED.source_rows,
                target_rows = EXCLUDED.target_rows,
                last_sync_run_id = EXCLUDED.last_sync_run_id,
                last_synced_at = now(),
                sync_status = EXCLUDED.sync_status,
                notes = EXCLUDED.notes
            """,
            (
                relation.schema,
                relation.name,
                relation.object_type,
                target_schema,
                relation.name,
                signature(columns),
                source_rows,
                target_rows,
                sync_run_id,
                status,
                "Initial private research snapshot; constraints/indexes intentionally not replicated.",
            ),
        )


def finish_sync_run(
    conn: psycopg.Connection,
    sync_run_id: int,
    status: str,
    tables_completed: int,
    rows_copied: int,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE medallio_admin.sync_runs
               SET finished_at = now(),
                   status = %s,
                   tables_completed = %s,
                   rows_copied = %s,
                   error_message = %s
             WHERE sync_run_id = %s
            """,
            (status, tables_completed, rows_copied, error_message, sync_run_id),
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Initial SELECT-only source snapshot from local medallio_dw to private Supabase schemas."
    )
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip target tables whose row count already equals the source. Mismatches still fail safely.",
    )
    p.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to source relation schema.table. May be repeated.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    schema_map: dict[str, str] = cfg["schema_map"]
    exclusions = set(cfg.get("exclude_relations", []))
    only = set(args.only)

    source_dsn = os.getenv("MEDALLIO_DSN")
    target_dsn = os.getenv("SUPABASE_DB_URL")
    if not source_dsn:
        raise SystemExit("Falta MEDALLIO_DSN.")
    if not target_dsn:
        raise SystemExit("Falta SUPABASE_DB_URL.")

    schemas = list(schema_map)
    with psycopg.connect(source_dsn, application_name="medallio_private_export") as source:
        source.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        relations = [
            r
            for r in discover_relations(source, schemas)
            if relation_id(r.schema, r.name) not in exclusions
            and (not only or relation_id(r.schema, r.name) in only)
        ]

        print(f"Source: {source.info.dbname}")
        print(f"Physical tables discovered: {len(relations)}")
        for r in relations:
            print(f"  {r.schema}.{r.name} -> {schema_map[r.schema]}.{r.name}")

        if args.dry_run:
            return 0

        with psycopg.connect(target_dsn, application_name="medallio_private_import") as target:
            for target_schema in sorted(set(schema_map.values())):
                ensure_target_schema_exists(target, target_schema)
            target.commit()

            sync_run_id = create_sync_run(target, schemas, len(relations))
            target.commit()

            completed = 0
            total_rows = 0
            try:
                for idx, relation in enumerate(relations, start=1):
                    target_schema = schema_map[relation.schema]
                    columns = discover_columns(source, relation)
                    if not columns:
                        print(f"[{idx}/{len(relations)}] SKIP {relation_id(relation.schema, relation.name)}: sin columnas")
                        continue

                    source_rows = table_count(source, relation.schema, relation.name)
                    ensure_target_table(target, relation, target_schema, columns)
                    target.commit()
                    existing_rows = table_count(target, target_schema, relation.name)

                    if existing_rows:
                        if args.resume and existing_rows == source_rows:
                            print(
                                f"[{idx}/{len(relations)}] OK existing "
                                f"{relation_id(relation.schema, relation.name)} rows={existing_rows}"
                            )
                            finish_table_event(
                                target,
                                sync_run_id,
                                relation,
                                target_schema,
                                columns,
                                source_rows,
                                existing_rows,
                                "skipped_equal",
                            )
                            completed += 1
                            total_rows += existing_rows
                            target.commit()
                            continue
                        raise RuntimeError(
                            f"Target {target_schema}.{relation.name} ya tiene {existing_rows} filas "
                            f"(source={source_rows}). No se borra ni trunca automáticamente."
                        )

                    start_table_event(target, sync_run_id, relation, target_schema, source_rows)
                    target.commit()
                    print(
                        f"[{idx}/{len(relations)}] COPY "
                        f"{relation.schema}.{relation.name} rows={source_rows}"
                    )

                    try:
                        copy_table(source, target, relation, target_schema, columns)
                        target_rows = table_count(target, target_schema, relation.name)
                        if target_rows != source_rows:
                            raise RuntimeError(
                                f"Reconciliation failed for {relation_id(relation.schema, relation.name)}: "
                                f"source={source_rows}, target={target_rows}"
                            )
                        finish_table_event(
                            target,
                            sync_run_id,
                            relation,
                            target_schema,
                            columns,
                            source_rows,
                            target_rows,
                            "success",
                        )
                        target.commit()
                        completed += 1
                        total_rows += target_rows
                    except Exception as exc:
                        target.rollback()
                        # Re-open event state without deleting copied data. A failed COPY
                        # is transactional, so the target table remains empty.
                        start_table_event(target, sync_run_id, relation, target_schema, source_rows)
                        finish_table_event(
                            target,
                            sync_run_id,
                            relation,
                            target_schema,
                            columns,
                            source_rows,
                            table_count(target, target_schema, relation.name),
                            "failed",
                            str(exc),
                        )
                        target.commit()
                        raise

                finish_sync_run(target, sync_run_id, "success", completed, total_rows)
                target.commit()
                print(f"DONE sync_run_id={sync_run_id} tables={completed} rows={total_rows}")
                return 0
            except Exception as exc:
                finish_sync_run(target, sync_run_id, "failed", completed, total_rows, str(exc))
                target.commit()
                raise


if __name__ == "__main__":
    raise SystemExit(main())
