-- Governed current feature contract for the first operational decision.
--
-- Prerequisites:
--   * core.fact_ciclo_comercial_unidad
--   * raw_cygnus.procesos / clientes_proyectos / proforma_unidad
--
-- The commercial state is NEVER reconstructed from a single RAW row here.
-- Lifecycle identity/state comes from CORE. RAW is used only for current
-- separation/delivery status, interaction metadata and proforma recency.
--
-- Eligibility v0.4:
--   * only open/active cycles whose proforma was first observed within the last
--     3 calendar months as of observed_at are eligible;
--   * proforma_first_seen_at = MIN(proforma_unidad.fecha_creacion) per proforma;
--   * an active Entrega process for the same codigo_proforma + codigo_unidad is
--     operational evidence that the case is already beyond fall-risk follow-up,
--     so it is excluded from scoring;
--   * a positive pago_ci marker is conversion evidence even when its dated
--     companion fecha_de_minuta is missing. Such rows are excluded from risk;
--   * unknown populated pago_ci markers are isolated as a blocked eligibility
--     bucket rather than silently interpreted.
--
-- Known feature limitations remain explicit in quality metadata:
--   * interaction_count_14d is a binary 0/1 proxy;
--   * has_pending_admin_block remains NULL until certified.

CREATE SCHEMA IF NOT EXISTS features;

CREATE OR REPLACE VIEW features.v_separation_fall_risk_candidate_universe AS
WITH proforma_recency AS (
    SELECT
        codigo_proforma::text AS codigo_proforma,
        MIN(fecha_creacion) AS proforma_first_seen_at
    FROM raw_cygnus.proforma_unidad
    WHERE codigo_proforma IS NOT NULL
    GROUP BY codigo_proforma::text
), active_entrega AS (
    -- Aggregate by the certified lifecycle grain so duplicate Entrega rows do
    -- not multiply candidates. procesos.id is not assumed globally unique.
    SELECT
        codigo_proforma::text AS codigo_proforma,
        codigo_unidad::text AS codigo_unidad,
        COUNT(*)::integer AS active_entrega_process_count,
        MAX(id) AS active_entrega_source_id
    FROM raw_cygnus.procesos
    WHERE lower(coalesce(nombre,'')) = 'entrega'
      AND lower(coalesce(estado,'')) = 'activo'
      AND codigo_proforma IS NOT NULL
      AND codigo_unidad IS NOT NULL
    GROUP BY codigo_proforma::text, codigo_unidad::text
)
SELECT
    'separacion:' || c.separacion_source_id::text AS separation_id,
    c.codigo_proforma,
    c.codigo_unidad,
    COALESCE(c.codigo_proyecto_ciclo, c.codigo_proyecto_unidad) AS codigo_proyecto,
    c.documento_cliente,
    c.asesor,
    c.fecha_separacion,
    c.analytics_refreshed_at AS observed_at,
    c.unidad_id,
    c.proyecto_id,
    c.proyecto_consistente,
    c.separacion_source_id,
    s.estado AS estado_separacion_actual,
    pr.proforma_first_seen_at,
    CASE
        WHEN pr.proforma_first_seen_at IS NOT NULL
         AND c.analytics_refreshed_at IS NOT NULL
        THEN GREATEST(
            0,
            c.analytics_refreshed_at::date - pr.proforma_first_seen_at::date
        )::integer
        ELSE NULL::integer
    END AS proforma_age_days,
    CASE
        WHEN c.analytics_refreshed_at IS NULL
            THEN 'BLOCKED_MISSING_OBSERVED_AT'
        WHEN pr.proforma_first_seen_at IS NULL
            THEN 'BLOCKED_MISSING_PROFORMA_DATE'
        WHEN pr.proforma_first_seen_at > c.analytics_refreshed_at
            THEN 'BLOCKED_PROFORMA_AFTER_OBSERVED_AT'
        WHEN ae.codigo_proforma IS NOT NULL
            THEN 'EXCLUDED_ACTIVE_ENTREGA_PROCESS'
        WHEN pr.proforma_first_seen_at < c.analytics_refreshed_at - interval '3 months'
            THEN 'EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS'
        WHEN c.pago_ci_marker_desconocido
            THEN 'BLOCKED_UNKNOWN_PAGO_CI_MARKER'
        WHEN c.pago_ci_marker_confirmado
            THEN 'EXCLUDED_PAGO_CI_MARKER_CONFIRMED'
        ELSE 'ELIGIBLE'
    END::text AS eligibility_status,
    'PROFORMA_RECENT_NOT_CONVERTED_AND_NO_ACTIVE_ENTREGA'::text AS eligibility_rule,
    3::integer AS eligibility_window_months,

    -- v0.3 evidence kept stable for backwards-compatible CREATE OR REPLACE.
    c.pago_ci_marker_raw,
    c.pago_ci_marker_confirmado,
    c.pago_ci_marker_desconocido,
    c.fecha_pago_ci,

    -- v0.4 delivery-process evidence appended after the stable v0.3 prefix.
    (ae.codigo_proforma IS NOT NULL) AS has_active_entrega_process,
    COALESCE(ae.active_entrega_process_count, 0)::integer AS active_entrega_process_count,
    ae.active_entrega_source_id
FROM core.fact_ciclo_comercial_unidad c
JOIN raw_cygnus.procesos s
  ON s.nombre = 'Separacion'
 AND s.id = c.separacion_source_id
 AND s.codigo_proforma::text = c.codigo_proforma
 AND s.codigo_unidad::text = c.codigo_unidad
LEFT JOIN proforma_recency pr
  ON pr.codigo_proforma = c.codigo_proforma
LEFT JOIN active_entrega ae
  ON ae.codigo_proforma = c.codigo_proforma
 AND ae.codigo_unidad = c.codigo_unidad
WHERE c.resultado_ciclo = 'ABIERTA'
  AND s.estado = 'Activo';

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
        u.*,
        cp.last_interaction_at,
        cp.total_interactions_observed,
        cp.documento_cliente AS interaction_match_documento
    FROM features.v_separation_fall_risk_candidate_universe u
    LEFT JOIN client_project_interaction cp
      ON cp.documento_cliente = u.documento_cliente::text
     AND cp.codigo_proyecto = u.codigo_proyecto
    WHERE u.eligibility_status = 'ELIGIBLE'
)
SELECT
    separation_id,
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    documento_cliente,
    asesor,
    fecha_separacion,
    observed_at,

    GREATEST(0, observed_at::date - fecha_separacion)::integer AS days_since_separation,

    GREATEST(
        0,
        observed_at::date - COALESCE(last_interaction_at::date, fecha_separacion)
    )::integer AS days_since_last_interaction,

    CASE
        WHEN last_interaction_at IS NOT NULL
         AND last_interaction_at >= observed_at - interval '14 days'
        THEN 1 ELSE 0
    END::integer AS interaction_count_14d,

    NULL::boolean AS has_pending_admin_block,
    last_interaction_at,
    total_interactions_observed,
    'LAST_PROJECT_INTERACTION_BINARY_PROXY'::text AS interaction_signal_mode,
    'NOT_YET_CERTIFIED'::text AS admin_signal_mode,
    'separation-fall-risk-current-v0.4.0'::text AS feature_contract_version,

    CASE
        WHEN separacion_source_id IS NULL
          OR codigo_proforma IS NULL
          OR codigo_unidad IS NULL
          OR unidad_id IS NULL
          OR proyecto_id IS NULL
          OR NOT proyecto_consistente
          OR fecha_separacion IS NULL
          OR observed_at IS NULL
          OR proforma_first_seen_at IS NULL
          OR observed_at::date < fecha_separacion
          OR proforma_first_seen_at > observed_at
          OR proforma_first_seen_at < observed_at - interval '3 months'
          OR pago_ci_marker_confirmado
          OR pago_ci_marker_desconocido
          OR has_active_entrega_process
          OR (
                last_interaction_at IS NOT NULL
            AND last_interaction_at > observed_at
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
            CASE WHEN observed_at IS NULL THEN 'MISSING_OBSERVED_AT' END,
            CASE WHEN proforma_first_seen_at IS NULL THEN 'MISSING_PROFORMA_FIRST_SEEN_AT' END,
            CASE
                WHEN observed_at IS NOT NULL AND fecha_separacion IS NOT NULL
                 AND observed_at::date < fecha_separacion
                THEN 'SEPARATION_AFTER_OBSERVED_AT'
            END,
            CASE
                WHEN proforma_first_seen_at IS NOT NULL AND observed_at IS NOT NULL
                 AND proforma_first_seen_at > observed_at
                THEN 'PROFORMA_AFTER_OBSERVED_AT'
            END,
            CASE
                WHEN proforma_first_seen_at IS NOT NULL AND observed_at IS NOT NULL
                 AND proforma_first_seen_at < observed_at - interval '3 months'
                THEN 'PROFORMA_OUTSIDE_RECENCY_WINDOW'
            END,
            CASE WHEN pago_ci_marker_confirmado THEN 'PAGO_CI_MARKER_CONFIRMED_MUST_NOT_BE_SCORED' END,
            CASE WHEN pago_ci_marker_desconocido THEN 'UNKNOWN_PAGO_CI_MARKER_VALUE' END,
            CASE WHEN has_active_entrega_process THEN 'ACTIVE_ENTREGA_PROCESS_MUST_NOT_BE_SCORED' END,
            CASE
                WHEN last_interaction_at IS NOT NULL AND observed_at IS NOT NULL
                 AND last_interaction_at > observed_at
                THEN 'INTERACTION_AFTER_OBSERVED_AT'
            END,
            CASE WHEN interaction_match_documento IS NULL THEN 'NO_CLIENT_PROJECT_INTERACTION_MATCH' END,
            'INTERACTION_COUNT_14D_BINARY_PROXY',
            'ADMIN_BLOCK_SIGNAL_NOT_CERTIFIED'
        ]::text[],
        NULL
    ) AS quality_reasons,

    proforma_first_seen_at,
    proforma_age_days,
    eligibility_status,
    eligibility_rule,
    eligibility_window_months,

    -- v0.3 columns kept stable.
    pago_ci_marker_raw,
    pago_ci_marker_confirmado,
    pago_ci_marker_desconocido,
    fecha_pago_ci,

    -- v0.4 columns appended.
    has_active_entrega_process,
    active_entrega_process_count,
    active_entrega_source_id
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
    MAX(observed_at) AS observed_at,

    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe)
        AS universe_candidates,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'ELIGIBLE') AS eligible_candidates,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS')
        AS excluded_proforma_older_than_3_months,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'BLOCKED_MISSING_PROFORMA_DATE')
        AS excluded_missing_proforma_date,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'BLOCKED_PROFORMA_AFTER_OBSERVED_AT')
        AS excluded_proforma_after_observed_at,
    COUNT(*) FILTER (
        WHERE proforma_first_seen_at IS NULL
           OR observed_at IS NULL
           OR proforma_first_seen_at > observed_at
           OR proforma_first_seen_at < observed_at - interval '3 months'
    )::bigint AS current_outside_proforma_recency_window,
    MIN(proforma_first_seen_at) AS oldest_eligible_proforma_first_seen_at,
    MAX(proforma_first_seen_at) AS newest_eligible_proforma_first_seen_at,
    3::integer AS eligibility_window_months,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'BLOCKED_MISSING_OBSERVED_AT')
        AS excluded_missing_observed_at,

    -- v0.3 conversion-marker safety metrics kept stable.
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'EXCLUDED_PAGO_CI_MARKER_CONFIRMED')
        AS excluded_pago_ci_marker_confirmed,
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'BLOCKED_UNKNOWN_PAGO_CI_MARKER')
        AS blocked_unknown_pago_ci_marker,
    COUNT(*) FILTER (
        WHERE pago_ci_marker_confirmado OR pago_ci_marker_desconocido
    )::bigint AS current_with_pago_ci_marker,

    -- v0.4 Entrega exclusion metrics appended after the stable v0.3 prefix.
    (SELECT COUNT(*)::bigint FROM features.v_separation_fall_risk_candidate_universe
      WHERE eligibility_status = 'EXCLUDED_ACTIVE_ENTREGA_PROCESS')
        AS excluded_active_entrega_process,
    COUNT(*) FILTER (WHERE has_active_entrega_process)::bigint
        AS current_with_active_entrega_process
FROM features.separation_fall_risk_current;
