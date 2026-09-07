from __future__ import annotations

from pathlib import Path

from ..decision_schema import ensure_decision_intelligence


def assert_lead_scoring_ready(conn) -> None:
    """Comprueba el contrato mínimo sin recrear tablas ni adquirir locks DDL."""
    required = (
        "features.lead_evidence",
        "model_control.model_runs",
        "model_control.model_aliases",
        "decision_intelligence.lead_scores",
    )
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT name, to_regclass(name) FROM unnest(%s::text[]) AS t(name)",
            (list(required),),
        )
        missing = [name for name, relation in cursor.fetchall() if relation is None]
    if missing:
        raise RuntimeError(
            "Lead Scoring no está inicializado. Ejecuta primero "
            "python scripts/lead_scoring.py init. Faltan: " + ", ".join(missing)
        )


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
