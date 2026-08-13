-- Tamaños.
SELECT 'fact_ventas_detalle' tabla,count(*) filas
FROM analytics.fact_ventas_detalle
UNION ALL
SELECT 'agg_ventas_mensual',count(*)
FROM analytics.agg_ventas_mensual
UNION ALL
SELECT 'fact_stock_ofertado_diario',count(*)
FROM analytics.fact_stock_ofertado_diario
UNION ALL
SELECT 'fact_absorcion_proyecto_diario',count(*)
FROM analytics.fact_absorcion_proyecto_diario
UNION ALL
SELECT 'dim_periodo_comercial_proyecto',count(*)
FROM analytics.dim_periodo_comercial_proyecto
UNION ALL
SELECT 'dim_fecha',count(*)
FROM analytics.dim_fecha;

-- Estado actual por proyecto.
SELECT DISTINCT ON (s.codigo_proyecto)
    s.codigo_proyecto,
    p.nombre_proyecto,
    s.fecha,
    s.stock_fin,
    s.separadas_activas,
    s.vendidas_acumuladas
FROM analytics.fact_stock_ofertado_diario s
LEFT JOIN analytics.dim_periodo_comercial_proyecto p
  USING(codigo_proyecto)
ORDER BY s.codigo_proyecto,s.fecha DESC;

-- Absorción actual.
SELECT DISTINCT ON (a.codigo_proyecto)
    a.codigo_proyecto,
    p.nombre_proyecto,
    a.fecha,
    a.stock_fin,
    a.separaciones_netas_30d,
    a.ventas_30d,
    a.absorcion_neta_30d,
    a.meses_stock_ventas_30d,
    a.dias_promedio_sep_venta_30d,
    a.tasa_caida_30d
FROM analytics.fact_absorcion_proyecto_diario a
LEFT JOIN analytics.dim_periodo_comercial_proyecto p
  USING(codigo_proyecto)
ORDER BY a.codigo_proyecto,a.fecha DESC;

-- QA reciente.
SELECT *
FROM observability.absorption_quality_results
ORDER BY checked_at DESC,quality_result_id DESC
LIMIT 30;
