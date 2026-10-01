#!/usr/bin/env python3
"""MEDALLIO AGENT PROTOCOL local utility.

Commands:
  status      Show current MAP + Git state.
  validate    Validate required files and state shape.
  checkpoint Capture Git evidence and generate a compact HANDOFF.md.
  bootstrap   Seed MAP files in another repository without overwriting files.

No command pushes, merges, calls external AI APIs, or reads secret files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROTOCOL = "MEDALLIO_AGENT_PROTOCOL"
VERSION = "1.0"

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/agentic/MEDALLIO_AGENT_PROTOCOL.md",
    "docs/agentic/PROJECT_STATE.md",
    "docs/agentic/ACTIVE_TASK.md",
    "docs/agentic/DECISIONS.md",
    "docs/agentic/HANDOFF.md",
    ".agent/state.json",
)

VALID_OWNERS = {"chatgpt", "claude", "human", "automation", "none"}
VALID_STATUSES = {
    "PLANNED",
    "IMPLEMENTING",
    "BLOCKED",
    "REVIEW_READY",
    "REVIEWING",
    "VALIDATION_REQUIRED",
    "DONE",
    "CANCELLED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def run_git(root: Path, *args: str, allow_failure: bool = False) -> str:
    command = ["git", "-C", str(root), *args]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0 and not allow_failure:
        message = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
        raise RuntimeError(f"{' '.join(command)}: {message}")
    return proc.stdout.strip()


def git_snapshot(root: Path) -> dict:
    branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = run_git(root, "rev-parse", "HEAD")
    porcelain = run_git(root, "status", "--porcelain")
    diff_stat = run_git(root, "diff", "--stat", allow_failure=True)
    staged_stat = run_git(root, "diff", "--cached", "--stat", allow_failure=True)
    recent = run_git(
        root,
        "log",
        "-5",
        "--pretty=format:%h %s",
        allow_failure=True,
    )
    return {
        "branch": branch,
        "head": head,
        "dirty": bool(porcelain),
        "changed_files": [line for line in porcelain.splitlines() if line.strip()],
        "diff_stat": diff_stat,
        "staged_diff_stat": staged_stat,
        "recent_commits": [line for line in recent.splitlines() if line.strip()],
    }


def state_path(root: Path) -> Path:
    return root / ".agent" / "state.json"


def load_state(root: Path) -> dict:
    path = state_path(root)
    if not path.exists():
        raise FileNotFoundError(f"Missing MAP state: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(root: Path, state: dict) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bullet_lines(items: Iterable[str], empty: str = "- None") -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return empty
    return "\n".join(f"- {item}" for item in values)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")

    try:
        state = load_state(root)
    except Exception as exc:
        errors.append(str(exc))
        return errors

    if state.get("protocol") != PROTOCOL:
        errors.append(f"state.protocol must be {PROTOCOL}")
    if not state.get("protocol_version"):
        errors.append("state.protocol_version is required")

    task = state.get("active_task")
    if not isinstance(task, dict):
        errors.append("state.active_task must be an object")
        return errors

    for key in ("id", "title", "status", "owner", "next_agent", "next_action"):
        if key not in task:
            errors.append(f"state.active_task.{key} is required")

    status = task.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"Unknown task status: {status}")

    for key in ("owner", "next_agent"):
        value = task.get(key)
        if value and value not in VALID_OWNERS:
            errors.append(f"Unknown {key}: {value}")

    return errors


def command_validate(root: Path) -> int:
    errors = validate(root)
    if errors:
        print("MAP validation: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"MAP validation: PASS ({PROTOCOL} v{VERSION})")
    return 0


def command_status(root: Path) -> int:
    state = load_state(root)
    git = git_snapshot(root)
    task = state.get("active_task", {})
    print("MEDALLIO AGENT PROTOCOL")
    print("=" * 42)
    print(f"Project      : {state.get('project', root.name)}")
    print(f"Protocol     : {state.get('protocol_version')}")
    print(f"Task         : {task.get('id')} — {task.get('title')}")
    print(f"Status       : {task.get('status')}")
    print(f"Owner        : {task.get('owner')}")
    print(f"Next agent   : {task.get('next_agent')}")
    print(f"Next action  : {task.get('next_action')}")
    print(f"Branch       : {git['branch']}")
    print(f"HEAD         : {git['head'][:12]}")
    print(f"Dirty        : {'yes' if git['dirty'] else 'no'}")
    return 0


def render_handoff(state: dict, git: dict, notes: list[str], tests: list[str]) -> str:
    task = state["active_task"]
    changed = git.get("changed_files", [])
    recent = git.get("recent_commits", [])
    return f"""# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL {state.get('protocol_version', VERSION)}
Generated at: {state.get('updated_at')}
Task: {task.get('id')} — {task.get('title')}
From: {task.get('owner')}
To: {task.get('next_agent')}
Status: {task.get('status')}
Branch: {git.get('branch')}
Commit at checkpoint: {git.get('head')}

## Exact next action

{task.get('next_action')}

## Working-tree state

Dirty: {'yes' if git.get('dirty') else 'no'}

### Changed files

{bullet_lines(changed)}

### Diff stat

```text
{git.get('diff_stat') or '(none)'}
```

### Staged diff stat

```text
{git.get('staged_diff_stat') or '(none)'}
```

## Validation / tests recorded for this checkpoint

{bullet_lines(tests)}

## Notes

{bullet_lines(notes)}

## Recent commits

{bullet_lines(recent)}

## Handoff rule

The receiving agent must inspect the real repository state and diff before trusting this summary. Code/runtime evidence and tests outrank this file.
"""


def command_checkpoint(root: Path, args: argparse.Namespace) -> int:
    errors = validate(root)
    if errors:
        print("Cannot checkpoint: MAP validation failed.", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    state = load_state(root)
    task = state["active_task"]

    if args.task_id:
        task["id"] = args.task_id
    task["owner"] = args.owner
    task["next_agent"] = args.next_agent
    task["status"] = args.status
    task["next_action"] = args.next_action

    git = git_snapshot(root)
    state["git"] = {
        **state.get("git", {}),
        "working_branch": git["branch"],
        "checkpoint_commit": git["head"],
        "dirty": git["dirty"],
    }
    state["updated_at"] = utc_now()
    state["validation"] = {
        "last_checked_at": state["updated_at"],
        "tests": args.test or [],
        "notes": args.note or [],
    }

    save_state(root, state)
    handoff = render_handoff(state, git, args.note or [], args.test or [])
    path = root / "docs" / "agentic" / "HANDOFF.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(handoff, encoding="utf-8")

    print(f"Checkpoint written: {path}")
    print(f"State written      : {state_path(root)}")
    print("No commit, push, or merge was performed.")
    return 0


def bootstrap_contents(project_name: str) -> dict[str, str]:
    return {
        "AGENTS.md": f"""# MEDALLIO AGENT PROTOCOL — Agent entrypoint

Project: {project_name}

Read:
1. docs/agentic/PROJECT_STATE.md
2. docs/agentic/ACTIVE_TASK.md
3. docs/agentic/DECISIONS.md
4. docs/agentic/HANDOFF.md
5. .agent/state.json

Authority: code/runtime > tests > real contracts > Git > MAP state > docs > conversations.

Never store secrets or raw PII in MAP files.
""",
        "CLAUDE.md": f"""# MEDALLIO AGENT PROTOCOL — Claude entrypoint

Project: {project_name}

@docs/agentic/PROJECT_STATE.md
@docs/agentic/ACTIVE_TASK.md
@docs/agentic/DECISIONS.md
@docs/agentic/HANDOFF.md

Inspect real Git/code/test state before edits. Never store secrets or raw PII in MAP files.
""",
        "docs/agentic/PROJECT_STATE.md": f"# Project State — {project_name}\n\nInitialize from verified repository evidence.\n",
        "docs/agentic/ACTIVE_TASK.md": "# Active Task\n\nTask ID: MAP-INIT\nStatus: PLANNED\nOwner: human\n\n## Next action\n\nDefine the first task.\n",
        "docs/agentic/DECISIONS.md": "# Decisions\n\nRecord durable architecture and operational decisions here.\n",
        "docs/agentic/HANDOFF.md": "# Latest Handoff\n\nNo handoff has been recorded yet.\n",
        ".agent/state.json": json.dumps(
            {
                "protocol": PROTOCOL,
                "protocol_version": VERSION,
                "project": project_name,
                "active_task": {
                    "id": "MAP-INIT",
                    "title": "Initialize agent protocol",
                    "status": "PLANNED",
                    "owner": "human",
                    "next_agent": "chatgpt",
                    "next_action": "Define the first task",
                },
                "git": {
                    "base_branch": None,
                    "working_branch": None,
                    "checkpoint_commit": None,
                    "dirty": None,
                },
                "validation": {
                    "last_checked_at": None,
                    "tests": [],
                    "notes": [],
                },
                "updated_at": utc_now(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    }


def command_bootstrap(source_root: Path, target: Path, project_name: str) -> int:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []

    for rel, content in bootstrap_contents(project_name).items():
        path = target / rel
        if path.exists():
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(rel)

    protocol_source = source_root / "docs" / "agentic" / "MEDALLIO_AGENT_PROTOCOL.md"
    protocol_target = target / "docs" / "agentic" / "MEDALLIO_AGENT_PROTOCOL.md"
    if protocol_target.exists():
        skipped.append("docs/agentic/MEDALLIO_AGENT_PROTOCOL.md")
    elif protocol_source.exists():
        protocol_target.parent.mkdir(parents=True, exist_ok=True)
        protocol_target.write_text(protocol_source.read_text(encoding="utf-8"), encoding="utf-8")
        created.append("docs/agentic/MEDALLIO_AGENT_PROTOCOL.md")

    tool_source = Path(__file__).resolve()
    tool_target = target / "tools" / "agent_handoff.py"
    if tool_target.exists():
        skipped.append("tools/agent_handoff.py")
    else:
        tool_target.parent.mkdir(parents=True, exist_ok=True)
        tool_target.write_text(tool_source.read_text(encoding="utf-8"), encoding="utf-8")
        created.append("tools/agent_handoff.py")

    print(f"MAP bootstrap target: {target}")
    print(f"Created: {len(created)}")
    for rel in created:
        print(f"  + {rel}")
    if skipped:
        print(f"Preserved existing: {len(skipped)}")
        for rel in skipped:
            print(f"  = {rel}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MEDALLIO AGENT PROTOCOL utility")
    parser.add_argument("--root", type=Path, default=None, help="Repository root; defaults to script parent repo")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("validate")

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--owner", required=True, choices=sorted(VALID_OWNERS))
    checkpoint.add_argument("--next-agent", required=True, choices=sorted(VALID_OWNERS))
    checkpoint.add_argument("--status", default="REVIEW_READY", choices=sorted(VALID_STATUSES))
    checkpoint.add_argument("--task-id")
    checkpoint.add_argument("--next-action", required=True)
    checkpoint.add_argument("--test", action="append", default=[], help="Test/evidence statement; repeatable")
    checkpoint.add_argument("--note", action="append", default=[], help="Checkpoint note; repeatable")

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--target", required=True, type=Path)
    bootstrap.add_argument("--project-name", required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = (args.root or repo_root_from_script()).resolve()

    try:
        if args.command == "status":
            return command_status(root)
        if args.command == "validate":
            return command_validate(root)
        if args.command == "checkpoint":
            return command_checkpoint(root, args)
        if args.command == "bootstrap":
            return command_bootstrap(root, args.target, args.project_name)
        parser.error(f"Unknown command: {args.command}")
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
