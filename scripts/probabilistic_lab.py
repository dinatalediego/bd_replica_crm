from __future__ import annotations

import argparse
import logging
from pathlib import Path

from replica_cygnus.probabilistic_lab.orchestrator import (
    ProbabilityCourseOrchestrator,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Medallio Probabilistic Lab")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--config", default="configs/probabilistic_lab.yml")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    lab = ProbabilityCourseOrchestrator(root, args.config)
    result = lab.run_all()
    print(f"Filas Medallio: {result['rows']}")
    print(f"Familias: {', '.join(result['families'])}")
    print(f"Resumen: {result['summary']}")
    print(f"PDF: {result['pdf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
