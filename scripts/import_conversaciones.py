"""Manual, local-only import. Run after replacing TXT files in conversaciones/."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.conversations import import_export
from replica_cygnus.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga incremental de exportaciones de WhatsApp a Medallio local.")
    parser.add_argument("--directory", type=Path, default=ROOT / "conversaciones")
    parser.add_argument("--file", type=Path, help="Un único TXT; por defecto todos los TXT de la carpeta.")
    args = parser.parse_args()
    paths = [args.file] if args.file else sorted(args.directory.glob("*.txt"))
    if not paths:
        print("[CONVERSACIONES] Sin TXT: no hay datos nuevos.")
        return 0
    settings = load_settings(require_source=False)
    with connect_postgres(settings) as conn:
        for path in paths:
            result = import_export(conn, path)
            print(json.dumps(asdict(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
