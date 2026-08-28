from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.raw_mercado_loader import load_raw_mercado


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga controlada CSV -> PostgreSQL raw_mercado.unidades")
    parser.add_argument("file", help="Ruta del CSV de mercado")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL"))
    parser.add_argument("--schema", default="raw_mercado")
    parser.add_argument("--table", default="unidades")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--append", action="store_true", help="No hace TRUNCATE antes de insertar")
    args = parser.parse_args()

    if not args.database_url:
        parser.error("Falta DATABASE_URL (o POSTGRES_URL) en el entorno o --database-url.")

    result = load_raw_mercado(
        args.database_url,
        args.file,
        schema_name=args.schema,
        table_name=args.table,
        delimiter=args.delimiter,
        encoding=args.encoding,
        snapshot=not args.no_snapshot,
        replace=not args.append,
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
