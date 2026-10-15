from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from medallio_evidence_outcome_v27 import (
    load_project_growth_state_from_db,
    load_ceo_growth_actions_from_db,
)


def main():
    states = load_project_growth_state_from_db("diagnostic")
    actions = load_ceo_growth_actions_from_db()

    print(f"[DB_BRIDGE] project_states={len(states)}")
    print(f"[DB_BRIDGE] governed_actions={len(actions)}")

    if not states:
        raise SystemExit(
            "No se pudo leer analytics.v_project_growth_state desde Ambassador. "
            "Revisa el bridge de conexión."
        )

    print("[DB_BRIDGE] L2 source ready: analytics.v_project_growth_state")
    for row in states[:5]:
        print(
            f"  {row.get('project_key')}: stock={row.get('stock_units')} "
            f"sales={row.get('sales_units')} gap={row.get('gap_value')} "
            f"action={row.get('suggested_action')}"
        )

    if actions:
        print("[DB_BRIDGE] CEO queue:")
        for row in actions[:5]:
            print(
                f"  {row.get('project_key')}: {row.get('decision')} "
                f"| owner={row.get('owner')} | urgency={row.get('urgency')}"
            )


if __name__ == "__main__":
    main()
