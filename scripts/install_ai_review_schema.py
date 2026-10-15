from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "115_ai_review" / "01_ai_review.sql"


def main() -> int:
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    with connect_postgres(load_settings(require_source=False)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, prepare=False)
        conn.commit()
    print("ai_review schema installed (opt-in).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
