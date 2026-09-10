from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"


@dataclass(frozen=True)
class Step:
    name: str
    args: tuple[str, ...]


class StepFailure(RuntimeError):
    def __init__(self, step: Step, returncode: int):
        super().__init__(f"{step.name} falló con código {returncode}")
        self.step = step
        self.returncode = returncode


def _logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dw_refresh")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(LOG_DIR / "dw_refresh.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


def _run(step: Step, logger: logging.Logger) -> None:
    logger.info("START %s", step.name)
    completed = subprocess.run(step.args, cwd=ROOT, check=False)
    if completed.returncode != 0:
        logger.error("FAIL %s rc=%s", step.name, completed.returncode)
        raise StepFailure(step, completed.returncode)
    logger.info("OK %s", step.name)


def _steps() -> tuple[Step, ...]:
    py = sys.executable
    return (
        Step(
            "01_raw_sync",
            (py, "-m", "replica_cygnus.cli", "sync"),
        ),
        Step(
            "02_schema_sync",
            (py, str(ROOT / "scripts" / "schema_sync.py")),
        ),
        Step(
            "03_core_commercial_refresh",
            (py, str(ROOT / "scripts" / "core_commercial.py"), "refresh"),
        ),
        Step(
            "04_unidades_powerbi_refresh",
            (py, str(ROOT / "scripts" / "unidades_powerbi.py")),
        ),
        Step(
            "05_absorption_phase_b_incremental",
            (py, str(ROOT / "src" / "absorption_phase_b" / "run_incremental.py")),
        ),
        Step(
            "06_core_lifecycle_contract",
            (py, str(ROOT / "scripts" / "core_commercial_lifecycle.py"), "init"),
        ),
        Step(
            "07_materialized_views",
            (py, str(ROOT / "scripts" / "refresh_materialized_views.py")),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh maestro de Medallio DW: RAW -> schema -> CORE -> analytics -> "
            "lifecycle -> materialized views -> observabilidad."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("hourly", "manual"),
        default="hourly",
        help="Etiqueta operativa del refresh.",
    )
    args = parser.parse_args()

    logger = _logger()
    logger.info("DW_REFRESH_BEGIN mode=%s", args.mode)

    failure: StepFailure | None = None
    try:
        for step in _steps():
            _run(step, logger)
    except StepFailure as exc:
        failure = exc
    finally:
        observe = Step(
            "99_observability",
            (
                sys.executable,
                "-m",
                "replica_cygnus.cli",
                "observe",
                "--mode",
                "hourly",
            ),
        )
        try:
            _run(observe, logger)
        except StepFailure as observe_exc:
            if failure is None:
                failure = observe_exc

    if failure is not None:
        logger.error(
            "DW_REFRESH_FAILED step=%s rc=%s",
            failure.step.name,
            failure.returncode,
        )
        return failure.returncode or 1

    logger.info("DW_REFRESH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
