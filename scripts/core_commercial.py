from __future__ import annotations

import argparse

from replica_cygnus.connections import connect_postgres
from replica_cygnus.core_commercial import (
    core_status,
    ensure_core_commercial,
    refresh_core_commercial,
)
from replica_cygnus.settings import load_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cygnus CORE Commercial Model v1"
    )
    parser.add_argument(
        "command",
        choices=["init", "refresh", "status"],
        help="init crea objetos; refresh reconstruye y reconcilia; status muestra conteos.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = load_settings()

    with connect_postgres(settings) as conn:
        if args.command == "init":
            ensure_core_commercial(conn, settings.project_root)
            print("CORE Commercial inicializado.")
            return 0

        if args.command == "refresh":
            result = refresh_core_commercial(conn, settings.project_root)
            print("CORE Commercial refrescado y reconciliado:")
            for key, value in result.items():
                print(f"  {key}: {value}")
            return 0

        ensure_core_commercial(conn, settings.project_root)
        result = core_status(conn)
        print("CORE Commercial status:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
