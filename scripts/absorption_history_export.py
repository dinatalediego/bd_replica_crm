from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.absorption_history_export import (
    export_multi_project_history,
    export_project_histories,
)


DEFAULT_PROJECTS = ["Fénix", "Urbanzen", "Tizón y Bueno"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exporta historia mensual de absorción/stock desde Medallio DW."
    )
    parser.add_argument(
        "--mode",
        choices=["project", "multi", "both"],
        default="both",
        help="project = un Excel por proyecto; multi = un Excel multiproyecto; both = ambos.",
    )
    parser.add_argument(
        "--projects",
        nargs="*",
        default=DEFAULT_PROJECTS,
        help="Proyectos. Default: Fénix, Urbanzen, Tizón y Bueno.",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Incluye todos los proyectos disponibles en la vista mensual.",
    )
    args = parser.parse_args()

    projects = None if args.all_projects else args.projects

    if args.mode in {"project", "both"}:
        print("Generando un Excel histórico por proyecto...")
        outputs = export_project_histories(projects=projects)
        for output in outputs:
            print(f"OK: {output}")

    if args.mode in {"multi", "both"}:
        print("Generando Excel histórico multiproyecto...")
        output = export_multi_project_history(projects=projects)
        print(f"OK: {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
