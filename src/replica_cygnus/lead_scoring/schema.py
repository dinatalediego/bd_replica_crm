from __future__ import annotations

from pathlib import Path

from ..decision_schema import ensure_decision_intelligence


def ensure_lead_scoring(conn, project_root: Path) -> None:
    """Inicializa dependencias y DDL versionado del primer loop ML de leads."""
    ensure_decision_intelligence(conn, project_root)
    path = project_root / "sql" / "init_lead_scoring.sql"
    sql_text = path.read_text(encoding="utf-8")
    statements = [chunk.strip() for chunk in sql_text.split(";") if chunk.strip()]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()
