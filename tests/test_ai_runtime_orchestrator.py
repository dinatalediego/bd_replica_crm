from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from replica_cygnus.ai_runtime.orchestrator import (
    JOB_GROUPS,
    _job_groups,
    groups_due,
    save_state,
)

LIMA = ZoneInfo("America/Lima")


def test_auto_first_run_executes_all_cadences(tmp_path: Path) -> None:
    now = datetime(2026, 10, 15, 21, 0, tzinfo=LIMA)
    assert groups_due(tmp_path, "auto", now) == ("hourly", "daily", "weekly")


def test_auto_after_daily_and_weekly_success_runs_only_hourly(tmp_path: Path) -> None:
    save_state(
        tmp_path,
        {
            "last_success": {"daily": "2026-10-15", "weekly": "2026-W42"},
            "last_run": None,
        },
    )
    now = datetime(2026, 10, 15, 22, 0, tzinfo=LIMA)
    assert groups_due(tmp_path, "auto", now) == ("hourly",)


def test_full_profile_is_explicit_and_complete(tmp_path: Path) -> None:
    assert groups_due(tmp_path, "full") == JOB_GROUPS


def test_automatic_jobs_never_promote_a_model(tmp_path: Path) -> None:
    groups = _job_groups(tmp_path)
    commands = [" ".join(job.command).lower() for jobs in groups.values() for job in jobs]
    assert not any(" promote " in f" {command} " for command in commands)
    assert any("train --evaluate" in command for command in commands)


def test_scoring_without_champion_is_soft_failure(tmp_path: Path) -> None:
    score_job = next(job for job in _job_groups(tmp_path)["hourly"] if job.name == "lead_score")
    assert score_job.soft_fail is True
