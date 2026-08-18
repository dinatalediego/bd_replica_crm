from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SQL_FILES = (
    "decision_engine/sql/03_decision_maturity_control.sql",
    "decision_engine/sql/04_seed_separation_policy.sql",
    "decision_engine/sql/05_candidate_universe_snapshot.sql",
    "decision_engine/sql/06_historical_fall_outcomes.sql",
    "decision_engine/sql/07_fall_reason_analysis_corpus.sql",
    "decision_engine/sql/08_training_outcome_contract.sql",
    "decision_engine/sql/09_transfer_lineage_audit.sql",
    "decision_engine/sql/10_point_in_time_training_set.sql",
    "decision_engine/sql/11_training_readiness_audit.sql",
    "decision_engine/sql/12_horizon_training_set.sql",
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

    print(
        "Decision maturity control instalado: PolicyOps + run audit + candidate snapshots "
        "+ historical fall outcomes + governed fall-reason corpus + supervised training target "
        "+ transfer lineage audit + point-in-time research set + readiness audit "
        "+ production-oriented 30-day horizon training set."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
