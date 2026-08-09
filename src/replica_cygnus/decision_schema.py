from __future__ import annotations

from pathlib import Path


def ensure_decision_intelligence(conn, project_root: Path) -> None:
    """Inicializa las tablas de Decision Intelligence usando SQL versionado.

    El archivo contiene DDL simple (sin funciones/procedimientos), por lo que se
    puede ejecutar statement por statement de forma explícita y auditable.
    """
    path = project_root / "sql" / "init_decision_intelligence.sql"
    sql_text = path.read_text(encoding="utf-8")
    statements = [chunk.strip() for chunk in sql_text.split(";") if chunk.strip()]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()
