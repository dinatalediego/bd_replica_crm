-- Solo lectura
SELECT current_database() AS database_actual, current_user AS usuario, current_timestamp AS ejecutado_en;
SELECT nspname AS schema_name FROM pg_namespace WHERE nspname IN ('raw_cygnus','analytics','features','model_control','decision_intelligence','etl_control','observability','experiments') ORDER BY 1;
SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE table_schema IN ('etl_control','observability') ORDER BY 1,2;
SELECT table_schema, table_name, ordinal_position, column_name, data_type FROM information_schema.columns WHERE table_schema IN ('etl_control','observability') ORDER BY 1,2,3;
