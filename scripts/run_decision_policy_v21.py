from __future__ import annotations

import argparse

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings
from replica_cygnus.lead_scoring.policy_v21 import (
    PolicyRunConfig,
    experiment_id,
    policy_run_id,
    preview_cohort,
    freeze_cohort,
    materialize_recommendations,
    run_status,
    frozen_assignments,
)


def _cfg(args) -> PolicyRunConfig:
    return PolicyRunConfig(
        run_key=args.run_key,
        cohort_size=args.cohort_size,
        treatment_share=args.treatment_share,
        selection_window_days=args.selection_window_days,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decision Policy V2.1 frozen cohort runner"
    )
    parser.add_argument(
        "command",
        choices=("preview", "freeze", "recommend", "status"),
    )
    parser.add_argument("--run-key", default="pilot_01")
    parser.add_argument("--cohort-size", type=int, default=100)
    parser.add_argument("--treatment-share", type=float, default=0.80)
    parser.add_argument("--selection-window-days", type=int, default=7)
    args = parser.parse_args()

    cfg = _cfg(args)
    settings = load_settings()

    print("experiment_id:", experiment_id())
    print("policy_run_id:", policy_run_id(cfg.run_key))
    print("run_key:", cfg.run_key)
    print("target allocation:", cfg.treatment_target_n, "/", cfg.control_target_n)

    with connect_postgres(settings) as conn:
        if args.command == "preview":
            frame = preview_cohort(conn, cfg)
            print("selected:", len(frame))
            if "treatment_group" in frame:
                print(frame.groupby("treatment_group").size().to_string())
            cols = [
                c for c in (
                    "policy_rank", "lead_id", "codigo_proyecto", "asesor",
                    "priority_band", "priority_score", "p_minuta_60d",
                    "treatment_group", "assignment_order",
                ) if c in frame.columns
            ]
            print(frame[cols].head(30).to_string(index=False))

        elif args.command == "freeze":
            result = freeze_cohort(conn, cfg)
            print(result)
            print(run_status(conn, policy_run_id(cfg.run_key)).to_string(index=False))

        elif args.command == "recommend":
            result = materialize_recommendations(conn, cfg)
            print(result)
            print(run_status(conn, policy_run_id(cfg.run_key)).to_string(index=False))

        elif args.command == "status":
            status = run_status(conn, policy_run_id(cfg.run_key))
            print(status.to_string(index=False) if len(status) else "RUN_NOT_CREATED")
            assignments = frozen_assignments(conn, policy_run_id(cfg.run_key))
            if len(assignments):
                print("\nAllocation:")
                print(assignments.groupby("treatment_group").size().to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
