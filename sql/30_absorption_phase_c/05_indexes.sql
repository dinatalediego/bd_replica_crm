CREATE INDEX IF NOT EXISTS ix_fact_ventas_project_date
ON analytics.fact_ventas_detalle(codigo_proyecto,fecha_venta);

CREATE INDEX IF NOT EXISTS ix_fact_stock_project_date
ON analytics.fact_stock_ofertado_diario(codigo_proyecto,fecha);

CREATE INDEX IF NOT EXISTS ix_abs_project_date
ON analytics.fact_absorcion_proyecto_diario(codigo_proyecto,fecha);

CREATE INDEX IF NOT EXISTS ix_agg_sales_month_project
ON analytics.agg_ventas_mensual(periodo_mes,codigo_proyecto);
