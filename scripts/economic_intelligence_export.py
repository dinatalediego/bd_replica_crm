from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.economic_intelligence.excel import export_absorption_economic_excel


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta absorción económica enriquecida desde Medallio DW.")
    parser.add_argument("--projects", nargs="*", default=None)
    args = parser.parse_args()
    path = export_absorption_economic_excel(projects=args.projects)
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
