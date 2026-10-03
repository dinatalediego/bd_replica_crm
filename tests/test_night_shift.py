from pathlib import Path

import yaml

from tools.night_shift import PRIORITY_RANK, sorted_candidates, validate


ROOT = Path(__file__).resolve().parents[1]


def test_night_shift_contracts_validate():
    assert validate(ROOT) == []


def test_queue_yaml_parses_and_has_unique_ids():
    queue = yaml.safe_load((ROOT / "agent_ops" / "NIGHT_QUEUE.yml").read_text(encoding="utf-8"))
    ids = [task["id"] for task in queue["tasks"]]
    assert len(ids) == len(set(ids))
    assert ids


def test_next_candidate_respects_date_and_priority():
    tasks = [
        {"id": "B", "status": "READY", "priority": "P1", "date": "2026-10-01"},
        {"id": "A", "status": "READY", "priority": "P0", "date": "2026-10-01"},
        {"id": "C", "status": "READY", "priority": "P0", "date": "2026-10-03"},
        {"id": "D", "status": "DONE", "priority": "P0", "date": "2026-10-01"},
    ]
    result = sorted_candidates(tasks, "2026-10-02")
    assert [task["id"] for task in result] == ["A", "B"]
    assert PRIORITY_RANK["P0"] < PRIORITY_RANK["P1"]
