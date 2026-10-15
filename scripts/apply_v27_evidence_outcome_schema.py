from __future__ import annotations

import os
from pathlib import Path


def find_repo_root():
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / ".env.example").exists():
            return candidate
    return p


def load_dotenv_simple(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def dsn_from_env():
    for key in ["MEDALLIO_DATABASE_URL", "DATABASE_URL", "POSTGRES_DSN", "PG_DSN"]:
        if os.getenv(key):
            return os.getenv(key)

    if all(os.getenv(k) for k in ["PGHOST", "PGDATABASE", "PGUSER"]):
        parts = [
            f"host={os.getenv('PGHOST')}",
            f"port={os.getenv('PGPORT', '5432')}",
            f"dbname={os.getenv('PGDATABASE')}",
            f"user={os.getenv('PGUSER')}",
        ]
        if os.getenv("PGPASSWORD"):
            parts.append(f"password={os.getenv('PGPASSWORD')}")
        return " ".join(parts)
    return None


def main():
    root = find_repo_root()
    load_dotenv_simple(root / ".env")

    dsn = dsn_from_env()
    if not dsn:
        raise SystemExit(
            "No encuentro conexión PostgreSQL. Usa MEDALLIO_DATABASE_URL / DATABASE_URL "
            "o PGHOST+PGDATABASE+PGUSER(+PGPASSWORD)."
        )

    sql_path = root / "sql" / "99_decision_intelligence" / "01_v27_evidence_outcome_gate.sql"
    if not sql_path.exists():
        raise SystemExit(f"Falta {sql_path}")

    import psycopg

    sql = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    print("v2.7 schema instalado.")
    print("Objetos principales:")
    print(" - analytics.v_project_growth_state")
    print(" - decision_intelligence.decision_ledger")
    print(" - decision_intelligence.action_log")
    print(" - decision_intelligence.outcome_ledger")
    print(" - experiments.baseline_challenger")
    print(" - model_control.evidence_gate")


if __name__ == "__main__":
    main()
