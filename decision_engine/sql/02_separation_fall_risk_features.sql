-- Governed current feature contract for the first operational decision.
--
-- Prerequisites merged in the MEDALLIO data foundation:
--   * core.fact_ciclo_comercial_unidad
--   * raw_cygnus.procesos
--   * raw_cygnus.clientes_proyectos
--
-- The commercial state is NEVER reconstructed from a single RAW row here.
-- Lifecycle identity/state comes from the certified CORE contract. RAW is used
-- only for the current separation status and interaction metadata.
--
-- v0.1 limitation, made explicit in quality metadata:
--   * interaction_count_14d is a binary 0/1 proxy derived from the latest
--     project-specific interaction timestamp. The baseline only tests zero vs
--     non-zero, so this is operationally sufficient for the first benchmark.
--   * has_pending_admin_block remains NULL until its business rule is certified.
--     The baseline treats NULL as False, while quality_status remains WARN.

CREATE SCHEMA IF NOT EXISTS features;

CREATE OR REPLACE VIEW features.separation_fall_risk_current AS
WITH client_project_interaction AS (
    SELECT
        documento_cliente::text AS documento_cliente,
        codigo_proyecto::text AS codigo_proyecto,
        MAX(fecha_ultima_interaccion) AS last_interaction_at,
        MAX(total_interacciones) AS total_interactions_observed
    FROM raw_cygnus.clientes_proyectos
    WHERE documento_cliente IS NOT NULL
      AND codigo_proyecto IS NOT NULL
    GROUP BY documento_cliente::text, codigo_proyecto::text
), candidate_base AS (
    SELECT
        c.*,
        s.estado AS estado_separacion_actual,
        cp.last_interaction_at,
        cp.total_interactions_observed,
        cp.documento_cliente AS interaction_match_documento
    FROM core.fact_ciclo_comercial_unidad c
    JOIN raw_cygnus.procesos s
      ON s.nombre = 'Separacion'
     AND s.id = c.separacion_source_id
     AND s.codigo_proforma::text = c.codigo_proforma
     AND s.codigo_unidad::text = c.codigo_unidad
    LEFT JOIN client_project_interaction cp
      ON cp.documento_cliente = c.documento_cliente::text
     AND cp.codigo_proyecto = COALESCE(c.codigo_proyecto_ciclo, c.codigo_proyecto_unidad)
    WHERE c.resultado_ciclo = 'ABIERTA'
      AND s.estado = 'Activo'
)
SELECT
    'separacion:' || separacion_source_id::text AS separation_id,
    codigo_proforma,
    codigo_unidad,
    COALESCE(codigo_proyecto_ciclo, codigo_proyecto_unidad) AS codigo_proyecto,
    documento_cliente,
    asesor,
    fecha_separacion,
    analytics_refreshed_at AS observed_at,

    GREATEST(
        0,
        analytics_refreshed_at::date - fecha_separacion
    )::integer AS days_since_separation,

    GREATEST(
        0,
        analytics_refreshed_at::date
        - COALESCE(last_interaction_at::date, fecha_separacion)
    )::integer AS days_since_last_interaction,

    CASE
        WHEN last_interaction_at IS NOT NULL
         AND last_interaction_at >= analytics_refreshed_at - interval '14 days'
        THEN 1
        ELSE 0
    END::integer AS interaction_count_14d,

    NULL::boolean AS has_pending_admin_block,
    last_interaction_at,
    total_interactions_observed,
    'LAST_PROJECT_INTERACTION_BINARY_PROXY'::text AS interaction_signal_mode,
    'NOT_YET_CERTIFIED'::text AS admin_signal_mode,
    'separation-fall-risk-current-v0.1.0'::text AS feature_contract_version,

    CASE
        WHEN separacion_source_id IS NULL
          OR codigo_proforma IS NULL
          OR codigo_unidad IS NULL
          OR unidad_id IS NULL
          OR proyecto_id IS NULL
          OR NOT proyecto_consistente
          OR fecha_separacion IS NULL
          OR analytics_refreshed_at IS NULL
          OR analytics_refreshed_at::date < fecha_separacion
          OR (
                last_interaction_at IS NOT NULL
            AND last_interaction_at > analytics_refreshed_at
          )
        THEN 'BLOCKED'
        ELSE 'WARN'
    END::text AS quality_status,

    array_remove(
        ARRAY[
            CASE WHEN separacion_source_id IS NULL THEN 'MISSING_SEPARATION_IDENTITY' END,
            CASE WHEN codigo_proforma IS NULL THEN 'MISSING_CODIGO_PROFORMA' END,
            CASE WHEN codigo_unidad IS NULL THEN 'MISSING_CODIGO_UNIDAD' END,
            CASE WHEN unidad_id IS NULL THEN 'UNRESOLVED_CORE_UNIDAD' END,
            CASE WHEN proyecto_id IS NULL THEN 'UNRESOLVED_CORE_PROYECTO' END,
            CASE WHEN NOT proyecto_consistente THEN 'INCONSISTENT_PROJECT_IDENTITY' END,
            CASE WHEN fecha_separacion IS NULL THEN 'MISSING_SEPARATION_DATE' END,
            CASE WHEN analytics_refreshed_at IS NULL THEN 'MISSING_OBSERVED_AT' END,
            CASE
                WHEN analytics_refreshed_at IS NOT NULL
                 AND fecha_separacion IS NOT NULL
                 AND analytics_refreshed_at::date < fecha_separacion
                THEN 'SEPARATION_AFTER_OBSERVED_AT'
            END,
            CASE
                WHEN last_interaction_at IS NOT NULL
                 AND analytics_refreshed_at IS NOT NULL
                 AND last_interaction_at > analytics_refreshed_at
                THEN 'INTERACTION_AFTER_OBSERVED_AT'
            END,
            CASE
                WHEN interaction_match_documento IS NULL
                THEN 'NO_CLIENT_PROJECT_INTERACTION_MATCH'
            END,
            'INTERACTION_COUNT_14D_BINARY_PROXY',
            'ADMIN_BLOCK_SIGNAL_NOT_CERTIFIED'
        ]::text[],
        NULL
    ) AS quality_reasons
FROM candidate_base;

CREATE OR REPLACE VIEW features.v_separation_fall_risk_health AS
SELECT
    COUNT(*)::bigint AS candidates,
    COUNT(DISTINCT separation_id)::bigint AS distinct_candidates,
    (COUNT(*) - COUNT(DISTINCT separation_id))::bigint AS duplicate_candidates,
    COUNT(*) FILTER (WHERE quality_status = 'OK')::bigint AS quality_ok,
    COUNT(*) FILTER (WHERE quality_status = 'WARN')::bigint AS quality_warn,
    COUNT(*) FILTER (WHERE quality_status = 'BLOCKED')::bigint AS quality_blocked,
    COUNT(*) FILTER (WHERE observed_at IS NULL)::bigint AS missing_observed_at,
    COUNT(*) FILTER (WHERE interaction_count_14d = 0)::bigint AS without_recent_interaction_signal,
    COUNT(*) FILTER (WHERE has_pending_admin_block IS NULL)::bigint AS admin_signal_pending_certification,
    MAX(observed_at) AS observed_at
FROM features.separation_fall_risk_current;
