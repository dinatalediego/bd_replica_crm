-- Commercial lifecycle certified contract v2.1.
--
-- IMPORTANT:
-- The temporal business logic is NOT duplicated here. The authoritative dated
-- lifecycle remains analytics.int_ciclo_comercial_unidad (Absorption Phase B).
-- CORE exposes a governed semantic contract over that certified result.
--
-- Proven conversion semantics:
--   * datos_extras.fecha_de_minuta is the effective dated field used by the
--     business Power Query as Fecha_PagoCI_pm; CORE exposes it as fecha_pago_ci.
--   * datos_extras.pago_ci is a categorical marker, not a date. The currently
--     known positive value is 'Pagó cuota inicial (Minuta)'.
--   * a positive marker without fecha_pago_ci is conversion evidence with
--     missing temporal precision. It must be excluded from fall-risk scoring.
--   * before 2026 only, the legacy Venta-process date remains the fallback dated
--     sale evidence when fecha_de_minuta is absent.
--   * from 2026 onward, the Venta-process date is process closure only.

CREATE SCHEMA IF NOT EXISTS core;

CREATE OR REPLACE VIEW core.fact_ciclo_comercial_unidad AS
WITH pago_ci_marker AS (
    SELECT DISTINCT ON (de.codigo)
        de.codigo::text AS codigo_proforma,
        de.id AS source_id,
        de.valor AS marker_raw
    FROM raw_cygnus.datos_extras de
    WHERE lower(de.entidad)='proforma'
      AND lower(de.nombre)='pago_ci'
    ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
)
SELECT
    c.codigo_proforma,
    c.codigo_unidad,
    u.unidad_id,
    c.codigo_proyecto AS codigo_proyecto_ciclo,
    u.codigo_proyecto AS codigo_proyecto_unidad,
    p.proyecto_id,
    (c.codigo_proyecto IS NULL OR c.codigo_proyecto = u.codigo_proyecto) AS proyecto_consistente,

    c.separacion_source_id,
    c.fecha_entrada_stock,
    c.fecha_separacion_raw,
    c.fecha_separacion,
    c.fecha_separacion_ajustada,

    c.venta_source_id,
    c.fecha_firma_legacy,
    c.datos_extras_fecha_minuta_id,
    c.fecha_de_minuta,
    c.fecha_venta,
    c.metodo_fecha_venta,

    c.primera_fecha_caida,
    c.ultima_fecha_caida,
    c.cantidad_anulaciones,
    c.resultado_ciclo,
    c.dias_separacion_venta,
    c.dias_separacion_caida,

    c.documento_cliente,
    c.asesor,
    c.tipo_unidad_principal,
    c.refreshed_at AS analytics_refreshed_at,

    -- Keep the v2 column names/order for CREATE OR REPLACE compatibility, but
    -- correct their semantics from the profiled source contract.
    m.source_id AS datos_extras_pago_ci_id,
    c.fecha_de_minuta AS fecha_pago_ci,
    c.fecha_firma_legacy AS fecha_cierre_proceso_venta,

    -- v2.1 marker evidence appended after the stable v2 prefix.
    m.marker_raw AS pago_ci_marker_raw,
    (
        lower(btrim(coalesce(m.marker_raw,''))) = lower('Pagó cuota inicial (Minuta)')
    ) AS pago_ci_marker_confirmado,
    (
        m.marker_raw IS NOT NULL
        AND btrim(m.marker_raw)<>''
        AND lower(btrim(m.marker_raw)) <> lower('Pagó cuota inicial (Minuta)')
    ) AS pago_ci_marker_desconocido
FROM analytics.int_ciclo_comercial_unidad c
LEFT JOIN core.dim_unidad u
    ON u.codigo_unidad = c.codigo_unidad
LEFT JOIN core.dim_proyecto p
    ON p.codigo_proyecto = u.codigo_proyecto
LEFT JOIN pago_ci_marker m
    ON m.codigo_proforma = c.codigo_proforma;

CREATE OR REPLACE VIEW core.v_ciclo_comercial_health AS
SELECT
    COUNT(*)::bigint AS ciclos,
    COUNT(DISTINCT (codigo_proforma, codigo_unidad))::bigint AS ciclos_distintos,
    (COUNT(*) - COUNT(DISTINCT (codigo_proforma, codigo_unidad)))::bigint AS ciclos_duplicados,
    COUNT(*) FILTER (WHERE unidad_id IS NULL)::bigint AS unidades_no_resueltas,
    COUNT(*) FILTER (WHERE proyecto_id IS NULL)::bigint AS proyectos_no_resueltos,
    COUNT(*) FILTER (WHERE NOT proyecto_consistente)::bigint AS proyectos_inconsistentes,
    COUNT(*) FILTER (WHERE resultado_ciclo = 'VENTA')::bigint AS ventas,
    COUNT(*) FILTER (WHERE resultado_ciclo = 'ABIERTA')::bigint AS abiertas,
    COUNT(*) FILTER (WHERE resultado_ciclo = 'CAIDA')::bigint AS caidas,
    COUNT(*) FILTER (WHERE resultado_ciclo NOT IN ('VENTA','ABIERTA','CAIDA'))::bigint AS resultados_no_validos,
    MAX(analytics_refreshed_at) AS ultimo_refresh_analytics,

    -- Stable v2 health prefix, now with corrected dated evidence semantics.
    COUNT(*) FILTER (
        WHERE resultado_ciclo='ABIERTA'
          AND fecha_pago_ci IS NOT NULL
          AND lower(coalesce(tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
    )::bigint AS abiertas_residenciales_con_pago_ci,
    COUNT(*) FILTER (
        WHERE resultado_ciclo='VENTA'
          AND metodo_fecha_venta='FECHA_DE_MINUTA'
    )::bigint AS ventas_por_pago_ci,
    COUNT(*) FILTER (
        WHERE resultado_ciclo='VENTA'
          AND metodo_fecha_venta='LEGACY_FECHA_FIRMA_PRE_2026'
    )::bigint AS ventas_legacy_pre_2026,
    COUNT(*) FILTER (
        WHERE fecha_separacion >= DATE '2026-01-01'
          AND resultado_ciclo='VENTA'
          AND lower(coalesce(tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
          AND metodo_fecha_venta <> 'FECHA_DE_MINUTA'
    )::bigint AS ventas_post_2026_sin_pago_ci,

    -- v2.1 marker-quality counters.
    COUNT(*) FILTER (
        WHERE pago_ci_marker_confirmado
          AND fecha_pago_ci IS NULL
          AND lower(coalesce(tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
    )::bigint AS marcadores_pago_ci_confirmados_sin_fecha,
    COUNT(*) FILTER (
        WHERE pago_ci_marker_desconocido
    )::bigint AS marcadores_pago_ci_desconocidos
FROM core.fact_ciclo_comercial_unidad;
