-- NO ejecutar a ciegas.
-- Primero revisar EXPLAIN y los índices actuales de RAW.

-- Los siguientes índices son para ANALYTICS, no RAW.
CREATE INDEX IF NOT EXISTS ix_int_ciclo_project_sep
ON analytics.int_ciclo_comercial_unidad(codigo_proyecto, fecha_separacion);

CREATE INDEX IF NOT EXISTS ix_int_ciclo_unit
ON analytics.int_ciclo_comercial_unidad(codigo_unidad);

CREATE INDEX IF NOT EXISTS ix_mov_stock_project_date
ON analytics.fact_movimientos_stock(codigo_proyecto, fecha_evento);

CREATE INDEX IF NOT EXISTS ix_mov_stock_unit_date
ON analytics.fact_movimientos_stock(codigo_unidad, fecha_evento);

CREATE INDEX IF NOT EXISTS ix_mov_stock_event_date
ON analytics.fact_movimientos_stock(tipo_evento, fecha_evento);
