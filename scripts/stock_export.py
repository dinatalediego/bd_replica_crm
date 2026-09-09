from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.stock_export import export_stock_excel, install_stock_export_sql
from replica_cygnus.stock_export.dependencies import ensure_unidades_view


DEFAULT_PROJECTS = ["Fénix", "Urbanzen", "Tizón y Bueno"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta stock disponible desde Medallio DW a Excel ejecutivo.")
    parser.add_argument(
        "--projects",
        nargs="*",
        default=DEFAULT_PROJECTS,
        help="Nombres de proyecto de analytics.v_stock_disponible_export. Sin valores usa el set post-feria.",
    )
    parser.add_argument(
        "--install-view",
        action="store_true",
        help="Instala/actualiza dependencias, reglas y la vista SQL antes de exportar.",
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="Instala/actualiza la capa SQL y termina sin generar Excel.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Exporta todos los proyectos configurados en analytics.stock_discount_rules.",
    )
    args = parser.parse_args()

    if args.install_view or args.install_only:
        print("[1/2] Validando dependencia canónica de unidades...")
        ensure_unidades_view()
        print("[2/2] Instalando capa SQL de stock exportable...")
        install_stock_export_sql()
        if args.install_only:
            print("OK: capa SQL lista para consumo.")
            return 0

    projects = None if args.all else args.projects
    print("Leyendo Medallio DW y generando Excel...")
    output = export_stock_excel(projects=projects)
    print(f"OK: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
