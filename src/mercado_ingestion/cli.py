from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

from .config import load_source
from .loader import default_snapshot_date, load_snapshot, read_and_prepare
from .schema import ensure_schema


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingesta de unidades del mercado")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Crea objetos raw_mercado de forma idempotente")

    for name in ("validate", "load"):
        command = subparsers.add_parser(name)
        command.add_argument("--file", required=True, type=Path)
        command.add_argument("--source-id", required=True)
        command.add_argument("--snapshot-date", type=date.fromisoformat)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = load_settings()

    if args.command == "init":
        with connect_postgres(settings) as conn:
            ensure_schema(conn)
        print("OK: esquema raw_mercado inicializado sin modificar raw_cygnus.")
        return 0

    source = load_source(settings.project_root, args.source_id)
    snapshot_date = args.snapshot_date or default_snapshot_date(source.timezone)
    if args.command == "validate":
        prepared = read_and_prepare(args.file, source)
        print(
            json.dumps(
                {
                    "estado": "VALID",
                    "source_id": source.source_id,
                    "fecha_snapshot": snapshot_date.isoformat(),
                    "filas": len(prepared.frame),
                    "columnas": list(prepared.frame.columns),
                    "advertencias": prepared.warnings,
                    "hash_archivo": prepared.file_hash,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    with connect_postgres(settings) as conn:
        result = load_snapshot(conn, args.file, source, snapshot_date)
    print(json.dumps({"estado": "SUCCESS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

