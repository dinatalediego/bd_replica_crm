-- Commercial lifecycle certified contract v1.
--
-- IMPORTANT:
-- The temporal business logic is NOT duplicated here. The authoritative
-- computation remains analytics.int_ciclo_comercial_unidad (Absorption Phase B).
-- CORE exposes a governed semantic contract over that certified result.

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
    c.refreshed_at AS analytics_refreshed_at
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
    MAX(analytics_refreshed_at) AS ultimo_refresh_analytics
FROM core.fact_ciclo_comercial_unidad;
