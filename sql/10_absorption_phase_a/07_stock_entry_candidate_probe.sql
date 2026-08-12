SELECT table_name,column_name,data_type FROM information_schema.columns
WHERE table_schema='raw_cygnus' AND table_name IN ('unidades','proforma_unidad','proyectos') AND (
 lower(column_name) LIKE '%fecha%crea%' OR lower(column_name) LIKE '%created%' OR lower(column_name) LIKE '%fecha%inicio%' OR lower(column_name) LIKE '%fecha%public%' OR lower(column_name) LIKE '%fecha%dispon%' OR lower(column_name) LIKE '%fecha%oferta%')
ORDER BY table_name,ordinal_position;

SELECT table_name,ordinal_position,column_name,data_type FROM information_schema.columns
WHERE table_schema='raw_cygnus' AND table_name IN ('unidades','proforma_unidad','proyectos') AND data_type IN ('date','timestamp without time zone','timestamp with time zone') ORDER BY table_name,ordinal_position;
