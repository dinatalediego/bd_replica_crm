from __future__ import annotations

from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


ROOT = Path(__file__).resolve().parents[1]
SQL_FILES = (
    ROOT / "sql" / "60_monthly_stock_movement" / "00_monthly_stock_movement.sql",
    ROOT / "sql" / "120_pocket_commercial" / "01_contract.sql",
)


def main() -> int:
    statements = []
    for path in SQL_FILES:
        if not path.exists():
            raise SystemExit(f"No existe {path}")
        statements.append(path.read_text(encoding="utf-8"))

    with connect_postgres(load_settings(require_source=False)) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                for sql_text in statements:
                    cur.execute(sql_text)
                cur.execute("SELECT count(*) FROM analytics.v_pocket_commercial_privacy_audit")
                pii_columns = int(cur.fetchone()[0])
                if pii_columns != 0:
                    raise RuntimeError(
                        f"Pocket privacy audit failed: {pii_columns} forbidden columns"
                    )
                cur.execute(
                    """
                    SELECT count(*), count(DISTINCT codigo_proyecto), max(fecha_corte)
                    FROM analytics.v_pocket_commercial_project_month
                    """
                )
                rows, projects, cutoff = cur.fetchone()

    print(
        f"Pocket commercial contract: OK rows={rows} projects={projects} cutoff={cutoff} pii_columns=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
