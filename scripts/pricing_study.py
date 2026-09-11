from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.pricing_study import generate_pricing_study


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera estudio ejecutivo de pricing inmobiliario desde Medallio DW."
    )
    parser.add_argument(
        "--project",
        help="Nombre o código parcial del proyecto. Si se omite, genera portafolio.",
    )
    parser.add_argument(
        "--install-sql",
        action="store_true",
        help="Instala/actualiza el mart pricing_analytics antes de reportar.",
    )
    parser.add_argument(
        "--capture-snapshot",
        action="store_true",
        help="Captura el snapshot diario de precios antes de reportar.",
    )
    parser.add_argument(
        "--snapshot-date",
        help="Fecha YYYY-MM-DD para snapshot manual. Por defecto CURRENT_DATE.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directorio alternativo de salida.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Ruta alternativa a config/pricing_study.yml.",
    )
    args = parser.parse_args()

    kwargs = {
        "project": args.project,
        "install_sql": args.install_sql,
        "capture_snapshot": args.capture_snapshot,
        "snapshot_date": args.snapshot_date,
    }
    if args.output_dir:
        kwargs["output_dir"] = args.output_dir
    if args.config:
        kwargs["config_path"] = args.config

    print("[pricing] Leyendo Medallio DW...")
    result = generate_pricing_study(**kwargs)
    print(f"PDF: {result.pdf_path}")
    print(f"PNG ejecutivo: {result.png_path}")
    print(f"Scorecard: {result.project_scorecard_csv}")
    print(f"Escenarios: {result.scenario_csv}")
    print(f"Acciones por unidad: {result.unit_actions_csv}")
    print(f"Evidencia: {result.evidence}")


if __name__ == "__main__":
    main()
