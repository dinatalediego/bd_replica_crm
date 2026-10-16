from __future__ import annotations

import argparse
import json
from pathlib import Path

from replica_cygnus.ai_runtime.orchestrator import JOB_GROUPS, groups_due, load_state, run_profile

ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Medallio AI Runtime: ejecuta los loops productivos de ML/forecast sin auto-promover modelos."
    )
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Ejecuta jobs reales de Python.")
    run.add_argument(
        "--profile",
        choices=("auto", "full", *JOB_GROUPS),
        default="auto",
        help="auto: hourly siempre, daily/weekly solo cuando corresponda.",
    )

    plan = sub.add_parser("plan", help="Muestra qué grupos ejecutaría auto en este momento.")
    plan.add_argument("--profile", choices=("auto", "full", *JOB_GROUPS), default="auto")
    sub.add_parser("status", help="Muestra el estado local persistente del runtime.")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "status":
        print(json.dumps(load_state(ROOT), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "plan":
        print(json.dumps({"profile": args.profile, "groups": groups_due(ROOT, args.profile)}, ensure_ascii=False, indent=2))
        return 0

    summary = run_profile(ROOT, args.profile)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, default=str))
    # BUSY/SKIP is healthy: the hourly scheduler will retry on its next invocation.
    return 1 if summary.status == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
