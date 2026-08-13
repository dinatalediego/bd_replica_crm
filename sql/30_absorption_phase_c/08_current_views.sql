CREATE OR REPLACE VIEW analytics.v_absorcion_proyecto_current AS
SELECT DISTINCT ON (a.codigo_proyecto)
    a.*,
    p.nombre_proyecto,
    p.fecha_inicio_comercial_observada
FROM analytics.fact_absorcion_proyecto_diario a
LEFT JOIN analytics.dim_periodo_comercial_proyecto p
  USING(codigo_proyecto)
ORDER BY a.codigo_proyecto,a.fecha DESC;

CREATE OR REPLACE VIEW analytics.v_stock_proyecto_current AS
SELECT DISTINCT ON (s.codigo_proyecto)
    s.*,
    p.nombre_proyecto
FROM analytics.fact_stock_ofertado_diario s
LEFT JOIN analytics.dim_periodo_comercial_proyecto p
  USING(codigo_proyecto)
ORDER BY s.codigo_proyecto,s.fecha DESC;
