-- Commercial lifecycle certified contract v2.
--
-- IMPORTANT:
-- The temporal business logic is NOT duplicated here. The authoritative
-- computation remains analytics.int_ciclo_comercial_unidad (Absorption Phase B).
-- CORE exposes a governed semantic contract over that certified result.
--
-- Sale-date semantics v2:
--   * pago_ci (datos_extras, proforma) is the primary commercial conversion date;
--   * before 2026 only, the legacy Venta-process date is the fallback when
--     pago_ci is absent;
--   * from 2026 onward, the Venta-process date means process closure and does
--     not by itself convert an opportunity to VENTA;
--   * fecha_de_minuta remains a separate milestone, not fecha_venta.

CREATE SCHEMA IF NOT EXISTS core;

CREATE OR REPLACE VIEW core.fact_ciclo_comercial_unidad AS
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

    -- v2 fields appended for CREATE OR REPLACE backwards compatibility.
    c.datos_extras_pago_ci_id,
    c.fecha_pago_ci,
    c.fecha_firma_legacy AS fecha_cierre_proceso_venta
FROM analytics.int_ciclo_comercial_unidad c
LEFT JOIN core.dim_unidad u
    ON u.codigo_unidad = c.codigo_unidad
LEFT JOIN core.dim_proyecto p
    ON p.codigo_proyecto = u.codigo_proyecto;

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

    -- v2 sale-date quality counters appended for backwards compatibility.
    COUNT(*) FILTER (
        WHERE resultado_ciclo='ABIERTA'
          AND fecha_pago_ci IS NOT NULL
          AND lower(coalesce(tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
    )::bigint AS abiertas_residenciales_con_pago_ci,
    COUNT(*) FILTER (
        WHERE resultado_ciclo='VENTA'
          AND metodo_fecha_venta='PAGO_CI_DATOS_EXTRAS'
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
          AND metodo_fecha_venta <> 'PAGO_CI_DATOS_EXTRAS'
    )::bigint AS ventas_post_2026_sin_pago_ci
FROM core.fact_ciclo_comercial_unidad;
