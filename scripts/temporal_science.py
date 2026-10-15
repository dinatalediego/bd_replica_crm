from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings
from replica_cygnus.temporal_science.service import ensure_schema, record_macro_result, run_internal, status

ROOT = Path(__file__).resolve().parents[1]


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Medallio Temporal Science Factory: perfiles, router de algoritmos, micro-modelos y coordinación macro."
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Crea únicamente los esquemas/vistas/tablas aditivas.")
    profile = sub.add_parser("profile", help="Perfila macro/micro y registra suitability; no llama al modelo macro.")
    profile.add_argument("--once-per-day", action="store_true")
    run = sub.add_parser("run", help="Ciclo cerrado: perfil + micro + forecasting macro existente.")
    run.add_argument("--once-per-day", action="store_true")
    run.add_argument("--no-macro", action="store_true", help="No ejecutar commercial_forecasting.py run.")
    run.add_argument("--output", type=Path, default=ROOT / "artifacts/temporal_science")
    stat = sub.add_parser("status")
    stat.add_argument("--limit", type=int, default=10)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    settings = load_settings(ROOT, require_source=False)
    with connect_postgres(settings) as conn:
        ensure_schema(conn, ROOT)
        if args.command == "init":
            print("Temporal Science Factory instalado. No se tocó RAW/CORE ni se consultó Redshift.")
            return 0
        if args.command == "status":
            print(_dumps(status(conn, args.limit)))
            return 0
        mode = "PROFILE" if args.command == "profile" else "CLOSED_LOOP"
        result = run_internal(
            conn,
            ROOT,
            ROOT / "artifacts/temporal_science" if args.command == "profile" else args.output,
            mode=mode,
            once_per_day=args.once_per_day,
        )
        print(_dumps(result))
        if result.get("run_id") is None or args.command == "profile" or args.no_macro:
            return 0
        run_id = result["run_id"]

    # Reuse the already-governed macro forecasting product. It has its own lock,
    # monthly idempotency, temporal validation, artifacts and frozen outcome measurement.
    cmd = [
        sys.executable,
        str(ROOT / "scripts/commercial_forecasting.py"),
        "run",
        "--once-per-month",
    ]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")

    with connect_postgres(settings) as conn:
        record_macro_result(
            conn,
            run_id,
            returncode=completed.returncode,
            stdout_tail=completed.stdout,
            stderr_tail=completed.stderr,
        )
    if completed.returncode != 0:
        print("La capa temporal/micro quedó registrada; el modelo macro falló y el run quedó PARTIAL.", file=sys.stderr)
        return completed.returncode or 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
