"""Explicit pilot commands; not called by scripts 40/41/42."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings
from replica_cygnus.lead_scoring.pilot import create_pilot, set_status, enroll, import_events


def read_csv(path, required_columns):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required_columns.issubset(reader.fieldnames or []):
            raise ValueError(f"Columnas requeridas: {sorted(required_columns)}")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("CSV mal formado: número de campos distinto a la cabecera")
    if len(rows) > 10000:
        raise ValueError("Dividir el archivo en lotes de máximo 10 000 filas")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Piloto Cygnus: asignación -> acción -> resultado revisado")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    create = sub.add_parser("create")
    create.add_argument("--protocol", required=True)
    create.add_argument("--operator", required=True)
    state = sub.add_parser("state")
    state.add_argument("--pilot", required=True)
    state.add_argument("--status", choices=["ACTIVE", "PAUSED", "CLOSED"], required=True)
    state.add_argument("--operator", required=True)
    assign = sub.add_parser("enroll")
    assign.add_argument("--pilot", required=True)
    assign.add_argument("--eligibility-csv", required=True)
    assign.add_argument("--operator", required=True)
    assign.add_argument("--apply", action="store_true", help="Persistir. Por defecto solo previsualiza.")
    imp = sub.add_parser("import")
    imp.add_argument("--pilot", required=True)
    imp.add_argument("--kind", choices=["actions", "outcomes"], required=True)
    imp.add_argument("--csv", required=True)
    imp.add_argument("--operator", required=True)
    status = sub.add_parser("status")
    status.add_argument("--pilot", required=True)
    args = parser.parse_args(argv)
    try:
        # Dedicated connection. Statement timeout bounds costly queries; contexts close transactions.
        with connect_postgres(load_settings()) as conn:
            conn.execute("SET statement_timeout='60s'")
            conn.execute("SET lock_timeout='5s'")
            conn.execute("SET TIME ZONE 'UTC'")
            if args.command == "init":
                conn.execute((ROOT / "sql/init_lead_pilot.sql").read_text(encoding="utf-8"))
                result = {"schema":"ready", "activated":False}
            elif args.command == "create":
                result = create_pilot(conn, json.loads(Path(args.protocol).read_text(encoding="utf-8-sig")), args.operator)
            elif args.command == "state":
                set_status(conn,args.pilot,args.status,args.operator)
                result = {"pilot":args.pilot,"status":args.status}
            elif args.command == "enroll":
                rows = read_csv(args.eligibility_csv, {"evidence_key","source_ref"})
                roster = {r["evidence_key"]:r["source_ref"] for r in rows}
                if len(roster)!=len(rows):
                    raise ValueError("CSV rechazado: evidence_key duplicado; no se ha asignado ninguna fila")
                result = enroll(conn,args.pilot,args.operator,roster,args.apply)
            elif args.command == "import":
                columns = {"assignment_id","source_ref"}
                columns |= {"event_id","action_at","action_type","result","owner","cost_pen"} if args.kind=="actions" else {"outcome_name","value","event_at","observed_through","verified_by"}
                result = import_events(conn,args.pilot,read_csv(args.csv,columns),args.kind,args.operator)
            else:
                from psycopg.rows import dict_row
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SELECT pilot_id,status,activated_at,approved_by FROM experiments.lead_pilots WHERE pilot_id=%s",(args.pilot,))
                    result = {"pilot":cur.fetchone()}
                    cur.execute("SELECT * FROM experiments.v_lead_pilot_summary WHERE pilot_id=%s",(args.pilot,))
                    result["summary"]=cur.fetchall()
                    cur.execute("SELECT * FROM experiments.v_lead_pilot_reconciliation WHERE pilot_id=%s ORDER BY started_at DESC LIMIT 10",(args.pilot,))
                    result["batches"]=cur.fetchall()
        # Print only after the outer transaction committed successfully.
        print(json.dumps(result,ensure_ascii=False,default=str,indent=2))
        return 2 if isinstance(result,dict) and result.get("rejected_rows",0) else 0
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
