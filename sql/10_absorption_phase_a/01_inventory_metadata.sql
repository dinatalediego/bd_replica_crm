-- Metadata, estimaciones y tamaños; evita COUNT(*) masivos
SELECT n.nspname AS schema_name, c.relname AS table_name, c.reltuples::bigint AS estimated_rows, pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size, pg_total_relation_size(c.oid) AS total_size_bytes
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='raw_cygnus' AND c.relkind IN ('r','p') ORDER BY pg_total_relation_size(c.oid) DESC;

SELECT table_name, ordinal_position, column_name, data_type, udt_name, is_nullable
FROM information_schema.columns WHERE table_schema='raw_cygnus' ORDER BY table_name, ordinal_position;

SELECT tc.table_name, tc.constraint_type, tc.constraint_name, string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
WHERE tc.table_schema='raw_cygnus' AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE') GROUP BY 1,2,3 ORDER BY 1,2,3;

SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='raw_cygnus' ORDER BY tablename,indexname;
