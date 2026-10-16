from __future__ import annotations

import json
import logging
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

LIMA = ZoneInfo("America/Lima")


@dataclass(frozen=True)
class Job:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 3600
    soft_fail: bool = False


@dataclass(frozen=True)
class JobResult:
    name: str
    returncode: int
    started_at: str
    finished_at: str
    stdout_tail: str
    stderr_tail: str
    soft_fail: bool

    @property
    def ok(self) -> bool:
        return self.returncode == 0 or self.soft_fail


@dataclass(frozen=True)
class RunSummary:
    profile: str
    started_at: str
    finished_at: str
    status: str
    results: tuple[JobResult, ...]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "results": [asdict(result) | {"ok": result.ok} for result in self.results],
        }


def _job_groups(root: Path) -> dict[str, tuple[Job, ...]]:
    py = sys.executable
    scripts = root / "scripts"
    lead = str(scripts / "lead_scoring.py")
    temporal = str(scripts / "temporal_science.py")
    forecast = str(scripts / "commercial_forecasting.py")
    return {
        "hourly": (
            Job("lead_capture_live", (py, lead, "capture", "--mode", "live"), 1800),
            # A missing champion should not stop evidence capture. Promotion remains human-governed.
            Job("lead_score", (py, lead, "score"), 1800, soft_fail=True),
            Job("lead_recommendations", (py, lead, "recommend"), 1200, soft_fail=True),
            Job("lead_outcomes", (py, lead, "outcomes"), 1200, soft_fail=True),
        ),
        "daily": (
            # This already coordinates micro models and the governed macro forecast.
            Job(
                "temporal_science_closed_loop",
                (py, temporal, "run", "--once-per-day"),
                7200,
            ),
            Job("forecast_measure", (py, forecast, "measure"), 1800, soft_fail=True),
            Job("lead_measure", (py, lead, "measure"), 1800, soft_fail=True),
        ),
        "weekly": (
            # Train/evaluate a challenger only. Never auto-promote to CHAMPION.
            Job(
                "lead_challenger_train_evaluate",
                (py, lead, "train", "--evaluate"),
                7200,
                soft_fail=True,
            ),
        ),
    }


# Public metadata for dashboards/tests without binding commands to a checkout path.
JOB_GROUPS = ("hourly", "daily", "weekly")


def _logger(root: Path) -> logging.Logger:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("medallio_ai_runtime")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_dir / "medallio_ai_runtime.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def _state_path(root: Path) -> Path:
    path = root / ".medallio" / "ai_runtime_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_state(root: Path) -> dict:
    path = _state_path(root)
    if not path.exists():
        return {"last_success": {}, "last_run": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_success": {}, "last_run": None}
    data.setdefault("last_success", {})
    return data


def save_state(root: Path, state: dict) -> None:
    path = _state_path(root)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _daily_key(now: datetime) -> str:
    return now.date().isoformat()


def _weekly_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def groups_due(root: Path, profile: str, now: datetime | None = None) -> tuple[str, ...]:
    if profile in JOB_GROUPS:
        return (profile,)
    if profile == "full":
        return JOB_GROUPS
    if profile != "auto":
        raise ValueError(f"Perfil desconocido: {profile}")

    now = now or datetime.now(LIMA)
    state = load_state(root)
    last = state.get("last_success", {})
    groups = ["hourly"]
    if last.get("daily") != _daily_key(now):
        groups.append("daily")
    if last.get("weekly") != _weekly_key(now):
        groups.append("weekly")
    return tuple(groups)


def _tail(value: str, limit: int = 6000) -> str:
    value = value or ""
    return value[-limit:]


def _run_job(root: Path, job: Job, logger: logging.Logger) -> JobResult:
    started = datetime.now(LIMA)
    logger.info("AI_JOB_START name=%s", job.name)
    try:
        completed = subprocess.run(
            list(job.command),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") + "\nTIMEOUT"
    except OSError as exc:
        returncode = 127
        stdout = ""
        stderr = str(exc)

    finished = datetime.now(LIMA)
    level = logging.INFO if returncode == 0 else (logging.WARNING if job.soft_fail else logging.ERROR)
    logger.log(level, "AI_JOB_END name=%s rc=%s soft_fail=%s", job.name, returncode, job.soft_fail)
    if stdout:
        logger.info("AI_JOB_STDOUT name=%s\n%s", job.name, _tail(stdout))
    if stderr:
        logger.log(level, "AI_JOB_STDERR name=%s\n%s", job.name, _tail(stderr))
    return JobResult(
        name=job.name,
        returncode=returncode,
        started_at=started.isoformat(timespec="seconds"),
        finished_at=finished.isoformat(timespec="seconds"),
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
        soft_fail=job.soft_fail,
    )


@contextmanager
def runtime_lock(root: Path):
    """Coordinate Windows, Docker and manual invocations through PostgreSQL."""
    settings = load_settings(root, require_source=False)
    with connect_postgres(settings) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Do not read a half-refreshed DW. If DW is busy, this attempt is skipped.
            cur.execute("SELECT pg_try_advisory_lock(hashtext('medallio.dw_refresh'))")
            dw_free = bool(cur.fetchone()[0])
            if dw_free:
                cur.execute("SELECT pg_advisory_unlock(hashtext('medallio.dw_refresh'))")
            if not dw_free:
                yield False, "DW_REFRESH_BUSY"
                return

            cur.execute("SELECT pg_try_advisory_lock(hashtext('medallio.ai_runtime'))")
            acquired = bool(cur.fetchone()[0])
            if not acquired:
                yield False, "AI_RUNTIME_BUSY"
                return
        try:
            yield True, "OK"
        finally:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext('medallio.ai_runtime'))")


def _mark_group_success(root: Path, group: str, now: datetime) -> None:
    if group == "hourly":
        return
    state = load_state(root)
    last = state.setdefault("last_success", {})
    if group == "daily":
        last[group] = _daily_key(now)
    elif group == "weekly":
        last[group] = _weekly_key(now)
    state["last_run"] = now.isoformat(timespec="seconds")
    save_state(root, state)


def _flatten(groups: Iterable[str], root: Path) -> Iterable[tuple[str, Job]]:
    configured = _job_groups(root)
    for group in groups:
        for job in configured[group]:
            yield group, job


def run_profile(root: Path, profile: str = "auto") -> RunSummary:
    root = root.resolve()
    logger = _logger(root)
    started = datetime.now(LIMA)
    groups = groups_due(root, profile, started)
    logger.info("AI_RUNTIME_BEGIN profile=%s groups=%s", profile, ",".join(groups))

    results: list[JobResult] = []
    group_results: dict[str, list[JobResult]] = {group: [] for group in groups}
    with runtime_lock(root) as (acquired, reason):
        if not acquired:
            logger.info("AI_RUNTIME_SKIP reason=%s", reason)
            finished = datetime.now(LIMA)
            return RunSummary(profile, started.isoformat(timespec="seconds"), finished.isoformat(timespec="seconds"), reason, ())

        current_group = None
        for group, job in _flatten(groups, root):
            if current_group is not None and group != current_group:
                previous = group_results[current_group]
                if all(result.ok for result in previous):
                    _mark_group_success(root, current_group, datetime.now(LIMA))
            current_group = group

            result = _run_job(root, job, logger)
            results.append(result)
            group_results[group].append(result)
            if not result.ok:
                logger.error("AI_RUNTIME_ABORT hard_failure=%s", job.name)
                break

        if current_group is not None and all(result.ok for result in group_results[current_group]):
            _mark_group_success(root, current_group, datetime.now(LIMA))

    hard_failures = [result for result in results if not result.ok]
    finished = datetime.now(LIMA)
    status = "FAILED" if hard_failures else "OK"
    logger.info("AI_RUNTIME_END status=%s jobs=%s", status, len(results))
    state = load_state(root)
    state["last_run"] = finished.isoformat(timespec="seconds")
    state["last_status"] = status
    state["last_profile"] = profile
    save_state(root, state)
    return RunSummary(
        profile=profile,
        started_at=started.isoformat(timespec="seconds"),
        finished_at=finished.isoformat(timespec="seconds"),
        status=status,
        results=tuple(results),
    )
