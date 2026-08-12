SELECT schemaname,tablename,attname,null_frac,n_distinct,most_common_vals,most_common_freqs
FROM pg_stats WHERE schemaname='raw_cygnus' AND tablename IN ('procesos','proforma_unidad','unidades') AND attname IN ('id','codigo_proforma','codigo_unidad','nombre','fecha_inicio','fecha_actualizacion','codigo') ORDER BY tablename,attname;
SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='raw_cygnus' AND tablename IN ('procesos','proforma_unidad','unidades') ORDER BY tablename,indexname;
EXPLAIN SELECT codigo_proforma,codigo_unidad,count(*) FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Venta','Anulacion') GROUP BY codigo_proforma,codigo_unidad;
