from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.platform_control import (
    ensure_platform_control,
    export_platform_status,
    platform_status_rows,
    refresh_platform_controls,
)
from replica_cygnus.settings import load_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cygnus Platform Command Center: readiness real desde PostgreSQL + Git."
    )
    parser.add_argument(
        "command",
        choices=["init", "refresh", "status"],
        help="init crea objetos; refresh recalcula controles; status muestra y exporta el snapshot.",
    )
    parser.add_argument(
        "--output",
        default="reports/platform_command_center.csv",
        help="CSV exportado para Power BI / Excel.",
    )
    return parser


def _print_status(rows: list[tuple]) -> None:
    if not rows:
        print("Sin aplicaciones registradas.")
        return
    print("\nCYGNUS PLATFORM COMMAND CENTER")
    print("=" * 92)
    print(f"{'Aplicación':<24} {'Capa':<18} {'Crit.':<9} {'Score':>7} {'Salud':<7} {'Done':>7}")
    print("-" * 92)
    for row in rows:
        app, layer, criticality, score, health, done, total, *_ = row
        pct = float(score or 0) * 100
        print(f"{app[:24]:<24} {layer[:18]:<18} {criticality:<9} {pct:6.1f}% {health:<7} {done:>2}/{total:<2}")


def main() -> int:
    args = _parser().parse_args()
    settings = load_settings()
    output = Path(args.output)
    if not output.is_absolute():
        output = settings.project_root / output

    with connect_postgres(settings) as conn:
        ensure_platform_control(conn, settings.project_root)
        if args.command in {"refresh", "status"}:
            refresh_platform_controls(conn, settings.project_root)
        rows = platform_status_rows(conn)
        _print_status(rows)
        exported = export_platform_status(conn, output)

    print(f"\nSnapshot exportado: {exported}")
    if args.command == "init":
        print("Siguiente paso: python scripts/platform_command_center.py refresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
