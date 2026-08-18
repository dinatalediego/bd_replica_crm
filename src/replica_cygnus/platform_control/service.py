from __future__ import annotations

import csv
import subprocess
from pathlib import Path

from psycopg import Connection


AUTOMATED_CONTROLS = {
    "postgres.schemas",
    "postgres.observability",
    "postgres.ml_governance",
    "postgres.decision_layer",
    "etl.control_table",
    "etl.recent_success",
    "etl.package",
    "git.repo",
    "git.secrets",
    "git.tests",
    "git.packaging",
    "quality.registry",
    "quality.snapshots",
    "quality.checks",
    "powerbi.pipeline_view",
    "powerbi.asset_view",
    "mlflow.registry_db",
}


def ensure_platform_control(conn: Connection, project_root: Path) -> None:
    """Create/upgrade Platform Command Center objects from versioned SQL."""
    sql_path = project_root / "sql" / "init_platform_control.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    with conn.cursor() as cursor:
        cursor.execute(sql_text, prepare=False)

    conn.commit()
    
def _schema_exists(conn: Connection, schema: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)",
            (schema,),
        )
        return bool(cursor.fetchone()[0])


def _relation_exists(conn: Connection, schema: str, relation: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (f"{schema}.{relation}",))
        return cursor.fetchone()[0] is not None


def _row_count(conn: Connection, schema: str, relation: str) -> int | None:
    if not _relation_exists(conn, schema, relation):
        return None
    with conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{relation}"')
        return int(cursor.fetchone()[0])


def _set_control(
    conn: Connection,
    control_key: str,
    status: str,
    *,
    evidence: str,
    details: str | None = None,
) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE platform_control.readiness_controls
               SET status = %s,
                   evidence = %s,
                   details = %s,
                   last_checked_at = now(),
                   updated_at = now()
             WHERE control_key = %s
            """,
            (status, evidence, details, control_key),
        )


def _git_output(project_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _refresh_git_controls(conn: Connection, project_root: Path) -> None:
    branch = _git_output(project_root, "rev-parse", "--abbrev-ref", "HEAD")
    sha = _git_output(project_root, "rev-parse", "--short", "HEAD")
    is_repo = branch is not None and sha is not None
    _set_control(
        conn,
        "git.repo",
        "DONE" if is_repo else "BLOCKED",
        evidence=f"branch={branch or 'unknown'}; commit={sha or 'unknown'}",
        details="Repositorio Git local detectado" if is_repo else "No se pudo ejecutar git en project_root",
    )

    gitignore = project_root / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    hardened = ".env.*" in gitignore_text and "!.env.example" in gitignore_text
    _set_control(
        conn,
        "git.secrets",
        "DONE" if hardened else "BLOCKED",
        evidence=str(gitignore),
        details="Variantes .env ignoradas; .env.example permitido" if hardened else "Endurecer .gitignore para .env.*",
    )

    tests_dir = project_root / "tests"
    tests_present = tests_dir.exists() and any(tests_dir.iterdir())
    _set_control(
        conn,
        "git.tests",
        "DONE" if tests_present else "IN_PROGRESS",
        evidence=str(tests_dir),
        details="Suite de tests presente" if tests_present else "No se encontraron tests",
    )

    pyproject = project_root / "pyproject.toml"
    _set_control(
        conn,
        "git.packaging",
        "DONE" if pyproject.exists() else "BLOCKED",
        evidence=str(pyproject),
        details="Paquete Python versionado" if pyproject.exists() else "Falta pyproject.toml",
    )
    _set_control(
        conn,
        "etl.package",
        "DONE" if pyproject.exists() else "BLOCKED",
        evidence="CLI replica-cygnus" if pyproject.exists() else str(pyproject),
    )


def _refresh_postgres_controls(conn: Connection) -> None:
    required_schemas = [
        "raw_cygnus",
        "staging",
        "core",
        "analytics",
        "etl_control",
        "features",
        "decision_intelligence",
        "model_control",
        "experiments",
        "observability",
    ]
    existing = [schema for schema in required_schemas if _schema_exists(conn, schema)]
    missing = sorted(set(required_schemas) - set(existing))
    schema_status = "DONE" if not missing else ("IN_PROGRESS" if len(existing) >= 6 else "BLOCKED")
    _set_control(
        conn,
        "postgres.schemas",
        schema_status,
        evidence=f"schemas={len(existing)}/{len(required_schemas)}",
        details="missing=" + ",".join(missing) if missing else "Todos los schemas mínimos existen",
    )

    obs_ok = _relation_exists(conn, "observability", "v_asset_health_current")
    _set_control(
        conn,
        "postgres.observability",
        "DONE" if obs_ok else "IN_PROGRESS",
        evidence="observability.v_asset_health_current",
    )

    ml_objects = _schema_exists(conn, "features") and _schema_exists(conn, "model_control") and _schema_exists(conn, "experiments")
    _set_control(
        conn,
        "postgres.ml_governance",
        "DONE" if ml_objects else "IN_PROGRESS",
        evidence="features + model_control + experiments",
    )

    decision_ok = _schema_exists(conn, "decision_intelligence")
    _set_control(
        conn,
        "postgres.decision_layer",
        "DONE" if decision_ok else "IN_PROGRESS",
        evidence="decision_intelligence",
    )

    sync_runs = _relation_exists(conn, "etl_control", "sync_runs")
    _set_control(
        conn,
        "etl.control_table",
        "DONE" if sync_runs else "BLOCKED",
        evidence="etl_control.sync_runs",
    )

    if sync_runs:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT finished_at,
                       EXTRACT(EPOCH FROM (now() - finished_at))/60.0 AS age_minutes
                  FROM etl_control.sync_runs
                 WHERE status = 'SUCCESS' AND finished_at IS NOT NULL
                 ORDER BY finished_at DESC
                 LIMIT 1
                """
            )
            row = cursor.fetchone()
        if row is None:
            status, evidence, details = "NOT_STARTED", "etl_control.sync_runs", "Aún no hay sincronizaciones SUCCESS"
        else:
            age = float(row[1])
            status = "DONE" if age <= 180 else ("IN_PROGRESS" if age <= 1440 else "BLOCKED")
            evidence = f"last_success={row[0].isoformat()}"
            details = f"age_minutes={age:.1f}"
        _set_control(conn, "etl.recent_success", status, evidence=evidence, details=details)
    else:
        _set_control(conn, "etl.recent_success", "BLOCKED", evidence="etl_control.sync_runs missing")

    registry_ok = _relation_exists(conn, "observability", "asset_registry")
    _set_control(
        conn,
        "quality.registry",
        "DONE" if registry_ok else "IN_PROGRESS",
        evidence="observability.asset_registry",
    )

    snapshot_count = _row_count(conn, "observability", "asset_snapshots")
    _set_control(
        conn,
        "quality.snapshots",
        "DONE" if snapshot_count and snapshot_count > 0 else "IN_PROGRESS",
        evidence=f"asset_snapshots={snapshot_count or 0}",
    )

    check_count = _row_count(conn, "observability", "quality_checks")
    _set_control(
        conn,
        "quality.checks",
        "DONE" if check_count and check_count > 0 else "IN_PROGRESS",
        evidence=f"quality_checks={check_count or 0}",
    )

    pipeline_view = _relation_exists(conn, "observability", "v_pipeline_runs")
    _set_control(
        conn,
        "powerbi.pipeline_view",
        "DONE" if pipeline_view else "IN_PROGRESS",
        evidence="observability.v_pipeline_runs",
    )

    asset_view = _relation_exists(conn, "observability", "v_asset_health_current")
    _set_control(
        conn,
        "powerbi.asset_view",
        "DONE" if asset_view else "IN_PROGRESS",
        evidence="observability.v_asset_health_current",
    )

    model_registry_ready = _relation_exists(conn, "model_control", "model_runs")
    _set_control(
        conn,
        "mlflow.registry_db",
        "IN_PROGRESS" if model_registry_ready else "NOT_STARTED",
        evidence="model_control.model_runs" if model_registry_ready else "MLflow aún no inicializado",
        details="La metadata interna existe; MLflow sigue siendo un componente por desplegar" if model_registry_ready else None,
    )


def refresh_platform_controls(conn: Connection, project_root: Path) -> None:
    """Refresh controls that can be proven automatically from PostgreSQL and Git."""
    ensure_platform_control(conn, project_root)
    _refresh_postgres_controls(conn)
    _refresh_git_controls(conn, project_root)
    conn.commit()


def platform_status_rows(conn: Connection) -> list[tuple]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT app_name,
                   platform_layer,
                   criticality,
                   readiness_score,
                   health_status,
                   controls_done,
                   controls_total,
                   next_milestone,
                   next_action,
                   blocking_reason,
                   last_checked_at
              FROM platform_control.v_application_readiness
             ORDER BY
                   CASE criticality
                       WHEN 'critical' THEN 1
                       WHEN 'high' THEN 2
                       WHEN 'medium' THEN 3
                       ELSE 4
                   END,
                   readiness_score,
                   app_name
            """
        )
        return cursor.fetchall()


def export_platform_status(conn: Connection, output_path: Path) -> Path:
    """Export the current command center snapshot for Power BI/Excel ingestion."""
    rows = platform_status_rows(conn)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "application",
        "platform_layer",
        "criticality",
        "readiness_score",
        "health_status",
        "controls_done",
        "controls_total",
        "next_milestone",
        "next_action",
        "blocking_reason",
        "last_checked_at",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return output_path
