from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def main():
    settings = load_settings()
    root = Path(settings.project_root)
    sql_path = root / "sql" / "102_evidence_outcome_persistence" / "01_persistence_ledgers.sql"

    if not sql_path.exists():
        raise SystemExit(f"Falta {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, prepare=False)
        conn.commit()

    required = [
        "model_control.evidence_gate",
        "analytics.project_growth_state_snapshot",
        "decision_intelligence.decision_ledger",
        "decision_intelligence.action_log",
        "decision_intelligence.outcome_ledger",
        "experiments.baseline_challenger",
    ]

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            print("[PERSISTENCE] objects:")
            missing = []
            for rel in required:
                cur.execute("SELECT to_regclass(%s)", (rel,))
                found = cur.fetchone()[0]
                print(f"  {rel}: {'OK' if found else 'MISSING'}")
                if not found:
                    missing.append(rel)

            # Guardrail: governed business view must survive untouched.
            cur.execute("SELECT to_regclass('analytics.v_project_growth_state')")
            governed = cur.fetchone()[0]
            print(
                "  analytics.v_project_growth_state: "
                + ("OK (governed view preserved)" if governed else "MISSING")
            )

    if missing:
        raise SystemExit(f"Faltan objetos: {missing}")

    print("\nEvidence/Outcome persistence installed safely.")


if __name__ == "__main__":
    main()
