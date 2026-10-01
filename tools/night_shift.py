#!/usr/bin/env python3
"""Governance utility for MEDALLIO NIGHT SHIFT OS.

This tool validates and summarizes the queue. It does not call AI models,
push Git commits, merge PRs, deploy production, or access secrets.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

VALID_STATUSES = {
    "READY",
    "CLAIMED",
    "IN_PROGRESS",
    "REVIEW_READY",
    "REVIEWING",
    "REWORK_REQUIRED",
    "READY_FOR_HUMAN",
    "BLOCKED",
    "NEEDS_SCOPING",
    "DONE",
    "CANCELLED",
}

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def queue_path(root: Path) -> Path:
    return root / "agent_ops" / "NIGHT_QUEUE.yml"


def policies_path(root: Path) -> Path:
    return root / "agent_ops" / "POLICIES.yml"


def budgets_path(root: Path) -> Path:
    return root / "agent_ops" / "BUDGETS.yml"


def week_path(root: Path) -> Path:
    return root / "agent_ops" / "WEEK_2026-10-01_07.yml"


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    required = [queue_path(root), policies_path(root), budgets_path(root), week_path(root)]
    for path in required:
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(root)}")

    if errors:
        return errors

    try:
        queue = load_yaml(queue_path(root))
        policies = load_yaml(policies_path(root))
        budgets = load_yaml(budgets_path(root))
        week = load_yaml(week_path(root))
    except Exception as exc:
        return [f"YAML parse error: {exc}"]

    tasks = queue.get("tasks") if isinstance(queue, dict) else None
    if not isinstance(tasks, list) or not tasks:
        errors.append("NIGHT_QUEUE.yml must contain a non-empty tasks list")
        return errors

    seen: set[str] = set()
    for idx, task in enumerate(tasks, start=1):
        label = f"task[{idx}]"
        if not isinstance(task, dict):
            errors.append(f"{label} must be an object")
            continue
        for key in ("id", "date", "priority", "repo", "title", "status", "objective", "acceptance", "next_action"):
            if not task.get(key):
                errors.append(f"{label}.{key} is required")
        task_id = task.get("id")
        if task_id in seen:
            errors.append(f"duplicate task id: {task_id}")
        elif task_id:
            seen.add(task_id)
        if task.get("status") not in VALID_STATUSES:
            errors.append(f"{task_id or label}: invalid status {task.get('status')}")
        if task.get("priority") not in PRIORITY_RANK:
            errors.append(f"{task_id or label}: invalid priority {task.get('priority')}")
        if not isinstance(task.get("acceptance"), list) or not task.get("acceptance"):
            errors.append(f"{task_id or label}: acceptance must be a non-empty list")

    if policies.get("default_workflow", {}).get("max_automatic_rework_cycles") != 1:
        errors.append("pilot requires max_automatic_rework_cycles == 1")

    if budgets.get("overnight_limits", {}).get("max_parallel_tasks") != 1:
        errors.append("pilot requires max_parallel_tasks == 1")

    daily = week.get("daily_focus", {})
    for task_id in [item.get("task") for item in daily.values() if isinstance(item, dict)]:
        if task_id not in seen:
            errors.append(f"week plan references unknown task: {task_id}")

    return errors


def sorted_candidates(tasks: list[dict], today: str | None = None) -> list[dict]:
    candidates = [t for t in tasks if t.get("status") == "READY"]
    if today:
        candidates = [t for t in candidates if str(t.get("date")) <= today]
    return sorted(
        candidates,
        key=lambda t: (
            PRIORITY_RANK.get(t.get("priority"), 99),
            str(t.get("date")),
            str(t.get("id")),
        ),
    )


def cmd_validate(root: Path) -> int:
    errors = validate(root)
    if errors:
        print("Night Shift validation: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Night Shift validation: PASS")
    return 0


def cmd_status(root: Path, today: str | None) -> int:
    errors = validate(root)
    if errors:
        return cmd_validate(root)

    queue = load_yaml(queue_path(root))
    tasks = queue["tasks"]
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1

    effective_today = today or date.today().isoformat()
    candidates = sorted_candidates(tasks, effective_today)

    print("MEDALLIO NIGHT SHIFT OS")
    print("=" * 44)
    print(f"Pilot        : {queue['pilot_window']['start']} -> {queue['pilot_window']['end']}")
    print(f"Today        : {effective_today}")
    print("States       : " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if candidates:
        next_task = candidates[0]
        print(f"Next READY   : {next_task['id']} [{next_task['priority']}] {next_task['title']}")
        print(f"Repository   : {next_task['repo']}")
        print(f"Next action  : {next_task['next_action']}")
    else:
        print("Next READY   : none eligible for current date")
    return 0


def cmd_next(root: Path, today: str | None) -> int:
    errors = validate(root)
    if errors:
        return cmd_validate(root)
    queue = load_yaml(queue_path(root))
    effective_today = today or date.today().isoformat()
    candidates = sorted_candidates(queue["tasks"], effective_today)
    if not candidates:
        print("NO_READY_TASK")
        return 0
    task = candidates[0]
    print(yaml.safe_dump(task, sort_keys=False, allow_unicode=True).strip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MEDALLIO Night Shift governance utility")
    parser.add_argument("--root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    status = sub.add_parser("status")
    status.add_argument("--today")
    nxt = sub.add_parser("next")
    nxt.add_argument("--today")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = (args.root or repo_root()).resolve()
    try:
        if args.command == "validate":
            return cmd_validate(root)
        if args.command == "status":
            return cmd_status(root, args.today)
        if args.command == "next":
            return cmd_next(root, args.today)
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
