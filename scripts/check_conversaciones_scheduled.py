"""One unattended attempt for the exact local Cygnus WhatsApp TXT."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.conversations import import_export
from replica_cygnus.conversations.schedule import run_scheduled_import
from replica_cygnus.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "conversaciones" / "Chat de WhatsApp con Cygnus - Ventas.txt"
LOG = ROOT / "conversaciones" / "scheduler_runs.jsonl"


def _log(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {"checked_at_local": datetime.now().astimezone().isoformat(), **record}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("[CONVERSACIONES] " + json.dumps(record, ensure_ascii=False))


def main() -> int:
    try:
        settings = load_settings(require_source=False)
        with connect_postgres(settings) as conn:
            result = run_scheduled_import(conn, FILE, import_export)
        _log(asdict(result))
        return 0
    except Exception as exc:
        _log({"status": "ERROR", "error_type": type(exc).__name__, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
