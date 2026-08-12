SELECT table_schema, table_name FROM information_schema.tables WHERE lower(table_name) LIKE '%dato%extra%' OR lower(table_name) LIKE '%extra%' ORDER BY 1,2;

SELECT table_schema, table_name,
 count(*) FILTER (WHERE lower(column_name)='entidad') AS has_entidad,
 count(*) FILTER (WHERE lower(column_name)='codigo') AS has_codigo,
 count(*) FILTER (WHERE lower(column_name)='nombre') AS has_nombre,
 count(*) FILTER (WHERE lower(column_name) IN ('valor','value','dato','valor_texto')) AS has_value_candidate
FROM information_schema.columns GROUP BY table_schema,table_name
HAVING count(*) FILTER (WHERE lower(column_name)='entidad')>0 AND count(*) FILTER (WHERE lower(column_name)='codigo')>0 AND count(*) FILTER (WHERE lower(column_name)='nombre')>0
ORDER BY 1,2;

SELECT table_schema,table_name,column_name,data_type FROM information_schema.columns WHERE lower(column_name) LIKE '%fecha%minuta%' ORDER BY 1,2,3;
SELECT table_schema,table_name,column_name,data_type FROM information_schema.columns WHERE lower(column_name) IN ('valor','value','dato','valor_texto') ORDER BY 1,2,3;
