from __future__ import annotations

from dataclasses import dataclass

from psycopg import sql

from .config import LeadScoringConfig


@dataclass(frozen=True)
class ResolvedSourceColumns:
    advisor: str | None
    channel: str | None
    medium: str | None


def _table_columns(conn, schema: str, table: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema=%s AND table_name=%s""",
            (schema, table),
        )
        return {str(row[0]) for row in cursor.fetchall()}


def _table_exists(conn, schema: str, table: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT EXISTS (SELECT 1 FROM information_schema.tables
                               WHERE table_schema=%s AND table_name=%s)
                   OR EXISTS (SELECT 1 FROM information_schema.views
                              WHERE table_schema=%s AND table_name=%s)""",
            (schema, table, schema, table),
        )
        return bool(cursor.fetchone()[0])


def _first_existing(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in columns), None)


def resolve_source_columns(conn, cfg: LeadScoringConfig) -> ResolvedSourceColumns:
    source = cfg.source
    columns = _table_columns(conn, source.schema, source.table)
    required = {source.id_column, source.decision_time_column,
                source.client_document_column, source.project_code_column}
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(f"{source.schema}.{source.table} no contiene columnas requeridas: " + ", ".join(missing))
    return ResolvedSourceColumns(
        advisor=_first_existing(columns, source.advisor_column_candidates),
        channel=_first_existing(columns, source.channel_column_candidates),
        medium=_first_existing(columns, source.medium_column_candidates),
    )


def _optional_text(alias: str, column: str | None) -> sql.Composable:
    if column is None:
        return sql.SQL("NULL::text")
    return sql.SQL("NULLIF(BTRIM({}.{}::text), '')").format(sql.Identifier(alias), sql.Identifier(column))


def capture_evidence(conn, cfg: LeadScoringConfig, mode: str = "live") -> int:
    """Captura evidencia append-only de decisiones de asignación de leads."""
    if mode not in {"live", "backfill"}:
        raise ValueError("mode debe ser live o backfill")
    if not _table_exists(conn, cfg.source.schema, cfg.source.table):
        raise RuntimeError(f"No existe {cfg.source.schema}.{cfg.source.table} en PostgreSQL local.")

    resolved = resolve_source_columns(conn, cfg)
    source = cfg.source
    date_filter = sql.SQL("")
    params: list[object] = []
    if mode == "live":
        date_filter = sql.SQL(" AND cp.{}::timestamptz >= current_date - (%s * interval '1 day')").format(
            sql.Identifier(source.decision_time_column))
        params.append(cfg.score_window_days)

    statement = sql.SQL(
        """
        INSERT INTO features.lead_evidence (
            evidence_key, lead_id, decision_at, captured_at, evidence_source,
            documento_cliente, codigo_proyecto, asesor, canal, medio,
            hour_of_day, day_of_week, is_weekend, feature_payload
        )
        SELECT
            md5(cp.{id_col}::text || '|' || cp.{decision_col}::timestamptz::text),
            cp.{id_col}::text, cp.{decision_col}::timestamptz, now(), {source_kind},
            NULLIF(BTRIM(cp.{document_col}::text), ''),
            NULLIF(BTRIM(cp.{project_col}::text), ''),
            {advisor_expr}, {channel_expr}, {medium_expr},
            EXTRACT(HOUR FROM cp.{decision_col}::timestamptz)::smallint,
            EXTRACT(ISODOW FROM cp.{decision_col}::timestamptz)::smallint,
            CASE WHEN EXTRACT(ISODOW FROM cp.{decision_col}::timestamptz) IN (6,7) THEN 1 ELSE 0 END::smallint,
            jsonb_build_object('source_schema', {schema_literal}, 'source_table', {table_literal},
                               'advisor_column', {advisor_literal}, 'channel_column', {channel_literal},
                               'medium_column', {medium_literal})
        FROM {schema}.{table} cp
        WHERE cp.{id_col} IS NOT NULL AND cp.{decision_col} IS NOT NULL
          AND NULLIF(BTRIM(cp.{document_col}::text), '') IS NOT NULL
          AND NULLIF(BTRIM(cp.{project_col}::text), '') IS NOT NULL
          {date_filter}
        ON CONFLICT (evidence_key) DO UPDATE SET
            captured_at = EXCLUDED.captured_at,
            evidence_source = CASE WHEN EXCLUDED.evidence_source='LIVE' THEN 'LIVE'
                                   ELSE features.lead_evidence.evidence_source END,
            features_refreshed_at = CASE
                WHEN COALESCE(EXCLUDED.asesor, features.lead_evidence.asesor)
                     IS DISTINCT FROM features.lead_evidence.asesor
                  THEN NULL
                ELSE features.lead_evidence.features_refreshed_at
            END,
            asesor = COALESCE(EXCLUDED.asesor, features.lead_evidence.asesor),
            canal = COALESCE(EXCLUDED.canal, features.lead_evidence.canal),
            medio = COALESCE(EXCLUDED.medio, features.lead_evidence.medio),
            feature_payload = features.lead_evidence.feature_payload || EXCLUDED.feature_payload
        """
    ).format(
        id_col=sql.Identifier(source.id_column), decision_col=sql.Identifier(source.decision_time_column),
        document_col=sql.Identifier(source.client_document_column), project_col=sql.Identifier(source.project_code_column),
        source_kind=sql.Literal("LIVE" if mode == "live" else "BACKFILL_INFERRED"),
        advisor_expr=_optional_text("cp", resolved.advisor), channel_expr=_optional_text("cp", resolved.channel),
        medium_expr=_optional_text("cp", resolved.medium), schema=sql.Identifier(source.schema), table=sql.Identifier(source.table),
        schema_literal=sql.Literal(source.schema), table_literal=sql.Literal(source.table),
        advisor_literal=sql.Literal(resolved.advisor), channel_literal=sql.Literal(resolved.channel),
        medium_literal=sql.Literal(resolved.medium), date_filter=date_filter,
    )
    with conn.cursor() as cursor:
        cursor.execute(statement, tuple(params))
        affected = int(cursor.rowcount or 0)
    conn.commit()
    return affected


def refresh_labels(conn, cfg: LeadScoringConfig) -> int:
    """Madura targets usando únicamente eventos posteriores a decision_at."""
    if not _table_exists(conn, "core", "fact_ciclo_comercial_unidad"):
        raise RuntimeError("Falta core.fact_ciclo_comercial_unidad. Ejecuta primero el ciclo comercial certificado.")
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE features.lead_evidence e
            SET separacion_14d = CASE
                    WHEN current_date >= e.decision_at::date + %s THEN
                        CASE WHEN EXISTS (
                            SELECT 1 FROM core.fact_ciclo_comercial_unidad c
                            WHERE c.documento_cliente=e.documento_cliente
                              AND COALESCE(c.codigo_proyecto_ciclo,c.codigo_proyecto_unidad)=e.codigo_proyecto
                              AND c.fecha_separacion>=e.decision_at::date
                              AND c.fecha_separacion<e.decision_at::date+%s
                        ) THEN 1 ELSE 0 END ELSE NULL END,
                minuta_60d = CASE
                    WHEN current_date >= e.decision_at::date + %s THEN
                        CASE WHEN EXISTS (
                            SELECT 1 FROM core.fact_ciclo_comercial_unidad c
                            WHERE c.documento_cliente=e.documento_cliente
                              AND COALESCE(c.codigo_proyecto_ciclo,c.codigo_proyecto_unidad)=e.codigo_proyecto
                              AND c.fecha_venta>=e.decision_at::date
                              AND c.fecha_venta<e.decision_at::date+%s
                        ) THEN 1 ELSE 0 END ELSE NULL END,
                labels_as_of=current_date,
                label_status=CASE WHEN current_date>=e.decision_at::date+%s THEN 'MATURED'
                                  WHEN current_date>=e.decision_at::date+%s THEN 'SEP_MATURED'
                                  ELSE 'PENDING' END
            WHERE e.labels_as_of IS NULL OR e.label_status <> 'MATURED'
            """,
            (cfg.sep_horizon_days, cfg.sep_horizon_days, cfg.minuta_horizon_days,
             cfg.minuta_horizon_days, cfg.minuta_horizon_days, cfg.sep_horizon_days),
        )
        affected = int(cursor.rowcount or 0)
    conn.commit()
    return affected


def historical_features_statement(cfg: LeadScoringConfig) -> str:
    """SQL set-based para features point-in-time; evita subconsultas por fila."""
    sep_h, minuta_h = int(cfg.sep_horizon_days), int(cfg.minuta_horizon_days)
    return f"""
        WITH calculated AS (
          SELECT
            evidence_key,
            COUNT(*) OVER (
              PARTITION BY documento_cliente ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '0.000001 seconds' PRECEDING
            )::integer AS client_prior_assignments_90d,
            EXTRACT(EPOCH FROM (
              decision_at - MAX(decision_at) OVER (
                PARTITION BY documento_cliente ORDER BY decision_at
                RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '0.000001 seconds' PRECEDING
              )
            )) / 86400.0 AS days_since_previous_assignment,
            COUNT(*) OVER (
              PARTITION BY codigo_proyecto ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '0.000001 seconds' PRECEDING
            )::integer AS project_leads_90d,
            AVG(separacion_14d::double precision) OVER (
              PARTITION BY codigo_proyecto ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '{sep_h} days' PRECEDING
            ) AS project_sep_rate_90d,
            AVG(minuta_60d::double precision) OVER (
              PARTITION BY codigo_proyecto ORDER BY decision_at
              RANGE BETWEEN INTERVAL '180 days' PRECEDING AND INTERVAL '{minuta_h} days' PRECEDING
            ) AS project_minuta_rate_180d,
            CASE WHEN asesor IS NULL THEN NULL ELSE COUNT(*) OVER (
              PARTITION BY asesor ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '0.000001 seconds' PRECEDING
            )::integer END AS advisor_leads_90d,
            CASE WHEN asesor IS NULL THEN NULL ELSE AVG(separacion_14d::double precision) OVER (
              PARTITION BY asesor ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '{sep_h} days' PRECEDING
            ) END AS advisor_sep_rate_90d,
            CASE WHEN asesor IS NULL THEN NULL ELSE AVG(minuta_60d::double precision) OVER (
              PARTITION BY asesor ORDER BY decision_at
              RANGE BETWEEN INTERVAL '180 days' PRECEDING AND INTERVAL '{minuta_h} days' PRECEDING
            ) END AS advisor_minuta_rate_180d,
            AVG(separacion_14d::double precision) OVER (
              ORDER BY decision_at
              RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '{sep_h} days' PRECEDING
            ) AS global_sep_rate_90d,
            AVG(minuta_60d::double precision) OVER (
              ORDER BY decision_at
              RANGE BETWEEN INTERVAL '180 days' PRECEDING AND INTERVAL '{minuta_h} days' PRECEDING
            ) AS global_minuta_rate_180d
          FROM features.lead_evidence
        )
        UPDATE features.lead_evidence e SET
          client_prior_assignments_90d=c.client_prior_assignments_90d,
          days_since_previous_assignment=c.days_since_previous_assignment,
          project_leads_90d=c.project_leads_90d,
          project_sep_rate_90d=c.project_sep_rate_90d,
          project_minuta_rate_180d=c.project_minuta_rate_180d,
          advisor_leads_90d=c.advisor_leads_90d,
          advisor_sep_rate_90d=c.advisor_sep_rate_90d,
          advisor_minuta_rate_180d=c.advisor_minuta_rate_180d,
          global_sep_rate_90d=c.global_sep_rate_90d,
          global_minuta_rate_180d=c.global_minuta_rate_180d,
          features_refreshed_at=now()
        FROM calculated c
        WHERE c.evidence_key=e.evidence_key
          AND e.features_refreshed_at IS NULL
    """


def refresh_historical_features(conn, cfg: LeadScoringConfig) -> int:
    """Calcula solo filas pendientes mediante ventanas SQL reutilizables."""
    with conn.cursor() as cursor:
        cursor.execute(historical_features_statement(cfg))
        affected = int(cursor.rowcount or 0)
    conn.commit()
    return affected
