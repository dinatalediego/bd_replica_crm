from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.monthly_stock_export import (
    export_monthly_stock_excel,
    install_monthly_stock_sql,
    validate_monthly_stock_dependencies,
)


DEFAULT_PROJECTS = ["Fénix", "Urbanzen", "Tizón y Bueno"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera Excel mensual de movimiento de stock y absorción desde Medallio DW."
    )
    parser.add_argument(
        "--month",
        help="Mes YYYY-MM. Si se omite, usa el mes actual.",
    )
    parser.add_argument(
        "--projects",
        nargs="*",
        default=DEFAULT_PROJECTS,
        help="Proyectos a incluir. Por defecto: Fénix, Urbanzen y Tizón y Bueno.",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Incluye todos los proyectos con datos del periodo.",
    )
    parser.add_argument(
        "--install-view",
        action="store_true",
        help="Valida dependencias e instala/actualiza las vistas del módulo antes de exportar.",
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="Sólo valida dependencias e instala las vistas; no genera Excel.",
    )
    args = parser.parse_args()

    if args.install_view or args.install_only:
        print("[1/2] Validando contrato de absorción/stock...")
        validate_monthly_stock_dependencies()
        print("[2/2] Instalando vistas de movimiento mensual...")
        install_monthly_stock_sql()
        print("OK: capa mensual lista en analytics.")
        if args.install_only:
            return 0

    projects = None if args.all_projects else args.projects
    print("Leyendo Medallio DW y generando Excel mensual...")
    output = export_monthly_stock_excel(period=args.month, projects=projects)
    print(f"OK: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
