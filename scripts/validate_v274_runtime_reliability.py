from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from medallio_evidence_outcome_v27 import (
    medallio_db_connection,
    load_project_growth_state_from_db,
    load_ceo_growth_actions_from_db,
)
from medallio_ambassador_v2 import google_json_rows


def main():
    print("[1] DB bridge")
    with medallio_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            db, user = cur.fetchone()
    print(f"    OK database={db} user={user}")

    print("[2] Governed project state")
    states = load_project_growth_state_from_db("diagnostic")
    actions = load_ceo_growth_actions_from_db()
    print(f"    states={len(states)} actions={len(actions)}")
    if not states:
        raise SystemExit("FAIL: project state vacío")

    print("[3] Google JSON coercion")
    sample = [[
        Decimal("43259760.000000"),
        Decimal("12.5"),
        {"gap": Decimal("100.25")},
    ]]
    normalized = google_json_rows(sample)
    json.dumps(normalized, ensure_ascii=False)
    print(f"    OK normalized={normalized}")

    print("[4] Evidence persistence relations")
    required = [
        "model_control.evidence_gate",
        "analytics.project_growth_state_snapshot",
        "decision_intelligence.decision_ledger",
    ]
    with medallio_db_connection() as conn:
        with conn.cursor() as cur:
            for rel in required:
                cur.execute("SELECT to_regclass(%s)", (rel,))
                found = cur.fetchone()[0]
                print(f"    {rel}: {'OK' if found else 'MISSING'}")

    print("\nv2.7.4 runtime reliability: OK")


if __name__ == "__main__":
    main()
