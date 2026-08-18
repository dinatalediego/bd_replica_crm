from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SQL_FILES = (
    "decision_engine/sql/03_decision_maturity_control.sql",
    "decision_engine/sql/04_seed_separation_policy.sql",
    "decision_engine/sql/05_candidate_universe_snapshot.sql",
)


def main() -> int:
    settings = load_settings()
    root = settings.project_root

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            for relative in SQL_FILES:
                path = root / relative
                print(f"[SQL] {relative}")
                cur.execute(path.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

    print("Decision maturity control instalado: PolicyOps + run audit + candidate snapshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
