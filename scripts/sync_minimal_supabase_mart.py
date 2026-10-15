"""Manual, allowlisted project-month export from local Medallio to private Supabase."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from replica_cygnus.supabase_mart import TARGET_FIELDS, build_packet, validate_packet


SOURCE_QUERY = """
SELECT codigo_proyecto, periodo_mes, mes_vida, mes_calendario, fecha_corte,
       mes_parcial, stock_inicial, ventas_mes, stock_final, dias_exposicion,
       unidades_revision
FROM analytics.comercial_proyecto_mes
WHERE codigo_proyecto = ANY(%s)
  AND periodo_mes >= %s
ORDER BY codigo_proyecto, periodo_mes
"""

UPSERT = """
INSERT INTO medallio_pilot.project_month
    (project_ref, period_month, life_month, calendar_month, source_cutoff,
     is_partial, stock_open, sales_units, stock_close, exposure_days,
     review_units, source_hash, data_origin)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (project_ref, period_month) DO UPDATE SET
    life_month = EXCLUDED.life_month,
    calendar_month = EXCLUDED.calendar_month,
    source_cutoff = EXCLUDED.source_cutoff,
    is_partial = EXCLUDED.is_partial,
    stock_open = EXCLUDED.stock_open,
    sales_units = EXCLUDED.sales_units,
    stock_close = EXCLUDED.stock_close,
    exposure_days = EXCLUDED.exposure_days,
    review_units = EXCLUDED.review_units,
    source_hash = EXCLUDED.source_hash,
    synced_at = now()
WHERE medallio_pilot.project_month.data_origin = EXCLUDED.data_origin
  AND (medallio_pilot.project_month.source_hash IS DISTINCT FROM EXCLUDED.source_hash
       OR medallio_pilot.project_month.source_cutoff IS DISTINCT FROM EXCLUDED.source_cutoff)
"""


def source_rows(dsn: str, projects: list[str], from_month: date) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(SOURCE_QUERY, (projects, from_month))
            rows = cur.fetchmany(1001)
            if len(rows) > 1000:
                raise ValueError("Pilot cap is 1000 rows")
            return rows


def publish(dsn: str, rows: list[dict]) -> int:
    import psycopg

    with psycopg.connect(dsn, sslmode="require") as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT, [tuple(row[field] for field in TARGET_FIELDS) for row in rows])
            refs = sorted({r["project_ref"] for r in rows})
            months = sorted({date.fromisoformat(r["period_month"]) for r in rows})
            cur.execute(
                """SELECT project_ref, period_month, source_hash
                   FROM medallio_pilot.project_month
                   WHERE project_ref = ANY(%s) AND period_month = ANY(%s)""",
                (refs, months),
            )
            target = {(ref, month.isoformat()): digest for ref, month, digest in cur.fetchall()}
            if any(target.get((row["project_ref"], row["period_month"])) != row["source_hash"] for row in rows):
                raise RuntimeError("Supabase reconciliation failed; transaction rolled back")
        conn.commit()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--project", action="append", default=[], help="Local project code; 1–3 per pilot")
    prepare.add_argument("--from-month", default="2024-01-01")
    prepare.add_argument("--fixture", type=Path, help="Synthetic source JSON; no database connection")
    prepare.add_argument("--output", type=Path, required=True)
    send = sub.add_parser("publish")
    send.add_argument("--packet", type=Path, required=True)
    send.add_argument("--approved-export", action="store_true")
    args = parser.parse_args()

    if args.command == "prepare":
        if args.output.exists():
            raise SystemExit("Output already exists")
        if args.fixture:
            if args.project:
                raise SystemExit("--fixture and --project are mutually exclusive")
            raw = json.loads(args.fixture.read_text(encoding="utf-8"))
            origin = "SYNTHETIC"
        else:
            if not 1 <= len(set(args.project)) <= 3:
                raise SystemExit("Choose 1–3 local project codes")
            dsn = os.getenv("MEDALLIO_DSN")
            if not dsn:
                raise SystemExit("MEDALLIO_DSN required")
            raw = source_rows(dsn, args.project, date.fromisoformat(args.from_month))
            origin = "MEDALLIO_AGGREGATE"
        key = os.getenv("MEDALLIO_EXPORT_HMAC_KEY", "").encode()
        packet = build_packet(raw, key, origin=origin)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(packet, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"Prepared {len(packet['rows'])} aggregate months from {len({r['project_ref'] for r in packet['rows']})} projects")
        return 0

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    rows = validate_packet(packet)
    if not args.approved_export:
        raise SystemExit("Explicit organizational export approval required: --approved-export")
    dsn = os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise SystemExit("SUPABASE_DB_URL required")
    print(f"Reconciled {publish(dsn, rows)} project-month rows in the private Supabase mart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
