from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path

from psycopg.types.json import Jsonb

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def fetch_dicts(cur, query, params=None):
    cur.execute(query, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def load_cfg(root: Path) -> dict:
    return json.loads(
        (root / "config" / "forecast_factory_v103.json").read_text(encoding="utf-8")
    )


def install(root: Path, conn):
    p = (
        root / "sql" / "123_forecast_factory_v103"
        / "01_forecast_factory_v103.sql"
    )
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def scalar(cur, query, params=None):
    cur.execute(query, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def evaluate(conn) -> dict:
    with conn.cursor() as cur:
        before = scalar(
            cur,
            "SELECT count(*) FROM analytics.forecast_evaluation_v1"
        ) or 0

        mature_candidates = scalar(
            cur,
            """
            SELECT count(*)
            FROM analytics.v_forecast_evaluation_candidate_v103
            WHERE
                maturity_status='MATURE'
                AND actual_id IS NOT NULL
            """
        ) or 0

        # Canonical evaluation. Interval metrics are NULL until uncertainty
        # calibration becomes evidence-supported.
        cur.execute(
            """
            INSERT INTO analytics.forecast_evaluation_v1(
                prediction_id,
                actual_id,
                evaluated_at,

                actual_value,
                prediction,
                naive_prediction,

                signed_error,
                absolute_error,
                ape,

                naive_signed_error,
                naive_absolute_error,
                naive_ape,

                interval_hit,
                interval_width,

                evidence_class,
                leakage_safe,

                metadata
            )
            SELECT
                c.prediction_id,
                c.actual_id,
                now(),

                c.actual_value,
                c.prediction,
                c.naive_prediction,

                (c.prediction-c.actual_value),
                abs(c.prediction-c.actual_value),

                CASE
                    WHEN abs(c.actual_value)>0
                    THEN abs(c.prediction-c.actual_value)/abs(c.actual_value)
                    ELSE NULL
                END,

                (c.naive_prediction-c.actual_value),
                abs(c.naive_prediction-c.actual_value),

                CASE
                    WHEN abs(c.actual_value)>0
                    THEN abs(c.naive_prediction-c.actual_value)/abs(c.actual_value)
                    ELSE NULL
                END,

                CASE
                    WHEN c.prediction_lower IS NULL
                      OR c.prediction_upper IS NULL
                    THEN NULL
                    ELSE c.actual_value BETWEEN c.prediction_lower AND c.prediction_upper
                END,

                CASE
                    WHEN c.prediction_lower IS NULL
                      OR c.prediction_upper IS NULL
                    THEN NULL
                    ELSE c.prediction_upper-c.prediction_lower
                END,

                c.evidence_class,

                (
                    c.evidence_class='PROSPECTIVE'
                    AND c.strict_prospective_order_valid
                    AND c.maturity_status='MATURE'
                ),

                jsonb_build_object(
                    'evaluator_version','v1.0.3',
                    'sample_policy','LATEST_WITHIN_MODEL_PROJECT_TARGET_LEAD_BUCKET',
                    'lead_time_bucket',c.lead_time_bucket,
                    'lead_time_days',c.lead_time_days,
                    'compatibility_status',c.compatibility_status,
                    'interval_status',c.interval_status
                )

            FROM analytics.v_forecast_evaluation_candidate_v103 c

            WHERE
                c.maturity_status='MATURE'
                AND c.actual_id IS NOT NULL

            ON CONFLICT(prediction_id)
            DO UPDATE SET
                actual_id=EXCLUDED.actual_id,
                evaluated_at=now(),

                actual_value=EXCLUDED.actual_value,
                prediction=EXCLUDED.prediction,
                naive_prediction=EXCLUDED.naive_prediction,

                signed_error=EXCLUDED.signed_error,
                absolute_error=EXCLUDED.absolute_error,
                ape=EXCLUDED.ape,

                naive_signed_error=EXCLUDED.naive_signed_error,
                naive_absolute_error=EXCLUDED.naive_absolute_error,
                naive_ape=EXCLUDED.naive_ape,

                interval_hit=EXCLUDED.interval_hit,
                interval_width=EXCLUDED.interval_width,

                evidence_class=EXCLUDED.evidence_class,
                leakage_safe=EXCLUDED.leakage_safe,
                metadata=EXCLUDED.metadata
            """
        )

        # Once a candidate is evaluated, its issuance record becomes EVALUATED.
        cur.execute(
            """
            UPDATE analytics.forecast_prediction_v1 p
            SET prediction_status='EVALUATED'
            FROM analytics.v_forecast_evaluation_candidate_v103 c
            WHERE
                p.prediction_id=c.prediction_id
                AND c.maturity_status='MATURE'
                AND c.actual_id IS NOT NULL
                AND p.prediction_status <> 'INVALIDATED'
            """
        )

        evidence_before = scalar(
            cur,
            """
            SELECT count(*)
            FROM model_control.forecast_evidence_v1
            WHERE evidence_type='MATURE_OUTCOME'
            """
        ) or 0

        # Outcome evidence is append-only by prediction; avoid duplicate evidence.
        cur.execute(
            """
            INSERT INTO model_control.forecast_evidence_v1(
                run_id,
                prediction_id,
                evidence_type,
                evidence_class,
                source_reference,
                verification_status,
                verified_at,
                verified_by,
                evidence_note
            )
            SELECT
                c.run_id,
                c.prediction_id,
                'MATURE_OUTCOME',
                c.evidence_class,
                'analytics.forecast_actual_v1:' || c.actual_id::text,
                'VERIFIED',
                now(),
                'forecast_factory_v103',
                'Closed actual matched through v1.0.3 maturity evaluator.'
            FROM analytics.v_forecast_evaluation_candidate_v103 c
            WHERE
                c.maturity_status='MATURE'
                AND c.actual_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM model_control.forecast_evidence_v1 e
                    WHERE
                        e.prediction_id=c.prediction_id
                        AND e.evidence_type='MATURE_OUTCOME'
                )
            """
        )

        after = scalar(
            cur,
            "SELECT count(*) FROM analytics.forecast_evaluation_v1"
        ) or 0

        evidence_after = scalar(
            cur,
            """
            SELECT count(*)
            FROM model_control.forecast_evidence_v1
            WHERE evidence_type='MATURE_OUTCOME'
            """
        ) or 0

    conn.commit()

    result = {
        "mature_candidates": int(mature_candidates),
        "evaluation_rows_before": int(before),
        "evaluation_rows_after": int(after),
        "new_evaluation_rows": int(max(after - before, 0)),
        "new_evidence_rows": int(max(evidence_after - evidence_before, 0)),
    }

    print(
        "[V1.0.3] maturity evaluator | "
        f"mature_candidates={result['mature_candidates']} | "
        f"evaluations={result['evaluation_rows_before']}->{result['evaluation_rows_after']} | "
        f"new_evidence={result['new_evidence_rows']}"
    )

    return result


def run_upstream(root: Path):
    script = root / "scripts" / "forecast_factory_v102.py"
    if not script.exists():
        raise RuntimeError(f"Missing upstream v1.0.2 script: {script}")

    for command in ("adapt-monthly", "load-actuals"):
        print(f"[V1.0.3] upstream v1.0.2 -> {command}")
        subprocess.run(
            [sys.executable, str(script), command],
            cwd=str(root),
            check=True,
        )


def start_cycle(conn, trigger_source: str) -> int:
    with conn.cursor() as cur:
        actual_before = scalar(
            cur,
            """
            SELECT count(*)
            FROM analytics.forecast_actual_v1
            WHERE target_name='sales_units'
            """
        ) or 0

        cur.execute(
            """
            INSERT INTO model_control.forecast_maturity_cycle_v103(
                cycle_status,
                trigger_source,
                actual_rows_before
            )
            VALUES('RUNNING',%s,%s)
            RETURNING cycle_id
            """,
            (trigger_source, actual_before),
        )
        cycle_id = cur.fetchone()[0]

    conn.commit()
    return cycle_id


def finish_cycle(conn, cycle_id: int, result: dict, status: str, message=None, error=None):
    with conn.cursor() as cur:
        actual_after = scalar(
            cur,
            """
            SELECT count(*)
            FROM analytics.forecast_actual_v1
            WHERE target_name='sales_units'
            """
        ) or 0

        latest_actual = scalar(
            cur,
            """
            SELECT max(actual_period)
            FROM analytics.forecast_actual_v1
            WHERE target_name='sales_units'
            """
        )

        next_unlock = scalar(
            cur,
            """
            SELECT min(expected_evidence_unlock)
            FROM analytics.v_forecast_evidence_calendar_detail_v103
            WHERE
                evidence_class='PROSPECTIVE'
                AND expected_evidence_unlock >= current_date
            """
        )

        cur.execute(
            """
            UPDATE model_control.forecast_maturity_cycle_v103
            SET
                finished_at=now(),
                cycle_status=%s,
                actual_rows_after=%s,
                mature_candidates=%s,
                evaluation_rows_before=%s,
                evaluation_rows_after=%s,
                new_evidence_rows=%s,
                latest_actual_period=%s,
                next_evidence_unlock=%s,
                message=%s,
                error_detail=%s
            WHERE cycle_id=%s
            """,
            (
                status,
                actual_after,
                result.get("mature_candidates"),
                result.get("evaluation_rows_before"),
                result.get("evaluation_rows_after"),
                result.get("new_evidence_rows"),
                latest_actual,
                next_unlock,
                message,
                error,
                cycle_id,
            ),
        )

    conn.commit()


def run_cycle(root: Path, conn, trigger_source: str):
    cycle_id = start_cycle(conn, trigger_source)
    result = {}

    try:
        run_upstream(root)
        result = evaluate(conn)

        finish_cycle(
            conn,
            cycle_id,
            result,
            "OK",
            message="Upstream actual refresh + maturity evaluation completed.",
        )

        print(f"[V1.0.3] cycle={cycle_id} OK")

    except Exception as exc:
        detail = traceback.format_exc()
        finish_cycle(
            conn,
            cycle_id,
            result,
            "ERROR",
            message=str(exc),
            error=detail,
        )
        print(f"[V1.0.3] cycle={cycle_id} ERROR")
        raise


def status(conn):
    with conn.cursor() as cur:
        ceo = fetch_dicts(
            cur,
            "SELECT * FROM analytics.v_forecast_ceo_evidence_status_v103"
        )
        ceo = ceo[0] if ceo else {}

        calendar = fetch_dicts(
            cur,
            """
            SELECT
                expected_evidence_unlock,
                target_period,
                lead_time_bucket,
                evaluation_candidates,
                incubating_candidates,
                outcome_due_candidates,
                blocked_scope_candidates,
                mature_ready_candidates,
                evaluated_candidates
            FROM analytics.v_forecast_evidence_calendar_v103
            WHERE evidence_class='PROSPECTIVE'
            ORDER BY expected_evidence_unlock,lead_time_bucket
            LIMIT 12
            """
        )

        scoreboard = fetch_dicts(
            cur,
            """
            SELECT
                model_name,
                lead_time_bucket,
                mature_pairs,
                distinct_target_periods,
                distinct_projects,
                wape,
                bias,
                naive_wape,
                skill_vs_naive,
                promotion_readiness,
                uncertainty_status
            FROM analytics.v_forecast_model_scoreboard_portfolio_v103
            ORDER BY lead_time_bucket,model_name
            """
        )

        champions = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_forecast_challenger_recommendation_v103
            ORDER BY lead_time_bucket
            """
        )

        cycles = fetch_dicts(
            cur,
            """
            SELECT
                cycle_id,started_at,finished_at,cycle_status,
                mature_candidates,new_evidence_rows,
                latest_actual_period,next_evidence_unlock
            FROM model_control.forecast_maturity_cycle_v103
            ORDER BY cycle_id DESC
            LIMIT 3
            """
        )

    print("[V1.0.3] CEO Evidence Status")
    if not ceo:
        print("  no CEO status available")
    else:
        print(
            "  prospective_predictions="
            f"{ceo.get('prospective_predictions')} | "
            f"evaluation_candidates={ceo.get('prospective_candidates')} | "
            f"evaluated_pairs={ceo.get('evaluated_prospective_pairs')} | "
            f"next_unlock={ceo.get('next_evidence_unlock')} | "
            f"pairs_next_unlock={ceo.get('expected_pairs_next_unlock')} | "
            f"champion={ceo.get('portfolio_champion_status')}"
        )

    print("[V1.0.3] Evidence Calendar")
    if not calendar:
        print("  no prospective calendar rows")
    for r in calendar:
        print(
            f"  {r['expected_evidence_unlock']} | target={r['target_period']} | "
            f"{r['lead_time_bucket']} | candidates={r['evaluation_candidates']} | "
            f"incubating={r['incubating_candidates']} | "
            f"due={r['outcome_due_candidates']} | "
            f"blocked={r['blocked_scope_candidates']} | "
            f"mature={r['mature_ready_candidates']} | "
            f"evaluated={r['evaluated_candidates']}"
        )

    print("[V1.0.3] Model Scoreboard")
    if not scoreboard:
        print("  no mature prospective scoreboard cells yet")
    for r in scoreboard:
        wape = "N/A" if r["wape"] is None else f"{float(r['wape'])*100:.1f}%"
        skill = "N/A" if r["skill_vs_naive"] is None else f"{float(r['skill_vs_naive'])*100:.1f}%"
        print(
            f"  {r['model_name']} | {r['lead_time_bucket']} | "
            f"pairs={r['mature_pairs']} | periods={r['distinct_target_periods']} | "
            f"projects={r['distinct_projects']} | WAPE={wape} | "
            f"Skill={skill} | {r['promotion_readiness']} | "
            f"{r['uncertainty_status']}"
        )

    print("[V1.0.3] Champion Status")
    if not champions:
        print("  NOT_YET_DECLARED")
    for r in champions:
        print(
            f"  {r['lead_time_bucket']} | "
            f"status={r['champion_status']} | "
            f"approved={r['approved_model_name']} | "
            f"recommended={r['recommended_model_name']}"
        )

    print("[V1.0.3] Last cycles")
    if not cycles:
        print("  no automated cycles yet")
    for r in cycles:
        print(
            f"  cycle={r['cycle_id']} | {r['cycle_status']} | "
            f"mature={r['mature_candidates']} | evidence={r['new_evidence_rows']} | "
            f"latest_actual={r['latest_actual_period']} | "
            f"next_unlock={r['next_evidence_unlock']}"
        )


def calendar(conn):
    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_forecast_evidence_calendar_v103
            WHERE evidence_class='PROSPECTIVE'
            ORDER BY expected_evidence_unlock,lead_time_bucket
            """
        )
    for r in rows:
        print(r)


def scoreboard(conn):
    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_forecast_model_scoreboard_portfolio_v103
            ORDER BY lead_time_bucket,model_name
            """
        )
    for r in rows:
        print(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "install",
            "evaluate",
            "run-cycle",
            "status",
            "calendar",
            "scoreboard",
        ],
        default="status",
    )
    parser.add_argument(
        "--trigger-source",
        default="MANUAL",
        choices=["MANUAL","TASK_SCHEDULER","PIPELINE","AMBASSADOR"],
    )
    args = parser.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[V1.0.3] schema installed.")
            status(conn)

        elif args.command == "evaluate":
            evaluate(conn)
            status(conn)

        elif args.command == "run-cycle":
            run_cycle(root, conn, args.trigger_source)
            status(conn)

        elif args.command == "calendar":
            calendar(conn)

        elif args.command == "scoreboard":
            scoreboard(conn)

        else:
            status(conn)


if __name__ == "__main__":
    main()
