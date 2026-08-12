from __future__ import annotations

from pathlib import Path

from psycopg import Connection


def ensure_observability(conn: Connection, project_root: Path) -> None:
    """Inicializa el esquema de observabilidad ejecutando DDL versionado."""
    sql_path = project_root / "sql" / "init_observability.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    statements = [chunk.strip() for chunk in sql_text.split(";") if chunk.strip()]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()
