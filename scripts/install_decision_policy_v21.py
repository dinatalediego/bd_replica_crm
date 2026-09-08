from __future__ import annotations

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SQL_FILE = "sql/init_decision_policy_v21.sql"

EXPECTED_TABLES = (
    ("experiments", "policy_runs"),
    ("experiments", "policy_run_assignments"),
)

EXPECTED_VIEWS = (
    ("experiments", "v_policy_run_status"),
    ("experiments", "v_policy_legacy_recommendations"),
    ("analytics", "v_pbi_policy_runs"),
    ("analytics", "v_pbi_policy_run_assignments"),
)

EXPECTED_FUNCTIONS = (
    ("experiments", "freeze_policy_run"),
    ("experiments", "guard_frozen_policy_run_assignment"),
    ("experiments", "guard_frozen_policy_run_config"),
)


def _exists(cur, schema: str, name: str, relkind: str | None = None) -> bool:
    if relkind is None:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname=%s AND c.relname=%s
            )
            """,
            (schema, name),
        )
    else:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname=%s AND c.relname=%s AND c.relkind=%s
            )
            """,
            (schema, name, relkind),
        )
    return bool(cur.fetchone()[0])


def main() -> int:
    settings = load_settings()
    root = settings.project_root
    sql_path = root / SQL_FILE

    if not sql_path.exists():
        raise FileNotFoundError(sql_path)

    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            print(f"[SQL] {SQL_FILE}")
            cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
        conn.commit()

        with conn.cursor() as cur:
            tables_ok = sum(_exists(cur, s, o, "r") for s, o in EXPECTED_TABLES)
            views_ok = sum(_exists(cur, s, o, "v") for s, o in EXPECTED_VIEWS)
            functions_ok = 0
            for schema, name in EXPECTED_FUNCTIONS:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM pg_proc p
                      JOIN pg_namespace n ON n.oid=p.pronamespace
                      WHERE n.nspname=%s AND p.proname=%s
                    )
                    """,
                    (schema, name),
                )
                functions_ok += int(bool(cur.fetchone()[0]))

            cur.execute(
                "SELECT COUNT(*) FROM experiments.v_policy_legacy_recommendations"
            )
            legacy_v2_n = int(cur.fetchone()[0])

    print(f"[VALIDATION] Tables: {tables_ok} / {len(EXPECTED_TABLES)}")
    print(f"[VALIDATION] Views: {views_ok} / {len(EXPECTED_VIEWS)}")
    print(f"[VALIDATION] Functions: {functions_ok} / {len(EXPECTED_FUNCTIONS)}")
    print(f"[RECONCILIATION] Legacy V2/V2.1 recommendations without run identity: {legacy_v2_n}")

    if tables_ok != len(EXPECTED_TABLES):
        raise RuntimeError("Decision Policy V2.1 tables validation failed")
    if views_ok != len(EXPECTED_VIEWS):
        raise RuntimeError("Decision Policy V2.1 views validation failed")
    if functions_ok != len(EXPECTED_FUNCTIONS):
        raise RuntimeError("Decision Policy V2.1 functions validation failed")

    print("Decision Policy V2.1 frozen-cohort contract installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
