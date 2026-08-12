-- No construye fecha_venta todavía
SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='raw_cygnus' AND table_name='procesos' AND lower(column_name) IN ('id','nombre','fecha_inicio','codigo_proforma','codigo_unidad','nombre_flujo','estado') ORDER BY ordinal_position;
SELECT count(*) AS ventas_evento,count(*) FILTER (WHERE fecha_inicio IS NULL) AS fecha_firma_null,min(fecha_inicio) AS primera_fecha_firma,max(fecha_inicio) AS ultima_fecha_firma FROM raw_cygnus.procesos WHERE nombre='Venta';
-- Tras localizar datos_extras, validar multiplicidad de fecha_de_minuta por codigo_proforma antes de fijar regla autoritativa.
