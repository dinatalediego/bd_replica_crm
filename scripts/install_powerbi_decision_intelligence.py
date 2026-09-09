from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SQL_FILES = (
    "sql/init_powerbi_decision_intelligence.sql",
)

EXPECTED_VIEWS = (
    "v_pbi_policy_registry",
    "v_pbi_policy_journey",
    "v_pbi_policy_funnel",
    "v_pbi_policy_capacity",
    "v_pbi_policy_adoption",
    "v_pbi_experiment_performance",
    "v_pbi_advisor_execution",
    "v_pbi_model_monitoring",
    "v_pbi_economic_value",
    "v_pbi_di_executive",
    "v_pbi_di_catalog",
)

EXPECTED_FUNCTIONS = (
    "fn_pbi_decision_window",
    "fn_pbi_policy_funnel",
)


def _validate_objects(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'analytics'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(EXPECTED_VIEWS),),
        )
        found_views = {row[0] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT p.proname
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'analytics'
              AND p.proname = ANY(%s)
            ORDER BY p.proname
            """,
            (list(EXPECTED_FUNCTIONS),),
        )
        found_functions = {row[0] for row in cur.fetchall()}

        missing_views = sorted(set(EXPECTED_VIEWS) - found_views)
        missing_functions = sorted(set(EXPECTED_FUNCTIONS) - found_functions)

        if missing_views or missing_functions:
            raise RuntimeError(
                "Power BI DI install incomplete. "
                f"Missing views={missing_views}; missing functions={missing_functions}"
            )

        cur.execute("SELECT * FROM analytics.v_pbi_di_executive")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("analytics.v_pbi_di_executive returned no row")

        cur.execute(
            """
            SELECT stage_order, stage_key, stage_rows
            FROM analytics.v_pbi_policy_funnel
            ORDER BY stage_order
            """
        )
        funnel_rows = cur.fetchall()
        if len(funnel_rows) != 8:
            raise RuntimeError(
                "analytics.v_pbi_policy_funnel expected 8 stages, "
                f"got {len(funnel_rows)}"
            )

        print("[VALIDATION] Views:", len(found_views), "/", len(EXPECTED_VIEWS))
        print(
            "[VALIDATION] Functions:",
            len(found_functions),
            "/",
            len(EXPECTED_FUNCTIONS),
        )
        print("[VALIDATION] Funnel stages:", len(funnel_rows))


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

        _validate_objects(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    policy_id,
                    evidence_n,
                    scores_n,
                    serving_scores_n,
                    eligible_current_n,
                    assigned_n,
                    recommendations_n,
                    actions_n,
                    sep_matured,
                    minuta_matured,
                    next_bottleneck
                FROM analytics.v_pbi_di_executive
                """
            )
            names = [item.name for item in cur.description or []]
            executive = dict(zip(names, cur.fetchone()))

    print("Power BI Decision Intelligence semantic layer installed.")
    print("Executive snapshot:", executive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
