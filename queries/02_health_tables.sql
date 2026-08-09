-- ============================================================
-- MEDALLIO DW - HEALTH CHECK DE TABLAS
-- Usa estadísticas de PostgreSQL. Es mucho más rápido que
-- ejecutar COUNT(*) sobre tablas grandes.
-- ============================================================

SELECT
    s.schemaname AS esquema,
    s.relname AS tabla,
    s.n_live_tup AS filas_estimadas,
    s.n_dead_tup AS filas_muertas,

    pg_size_pretty(
        pg_total_relation_size(
            quote_ident(s.schemaname) || '.' || quote_ident(s.relname)
        )
    ) AS tamano_total,

    pg_size_pretty(
        pg_relation_size(
            quote_ident(s.schemaname) || '.' || quote_ident(s.relname)
        )
    ) AS tamano_datos,

    (
        SELECT COUNT(*)
        FROM information_schema.columns c
        WHERE c.table_schema = s.schemaname
          AND c.table_name = s.relname
    ) AS numero_columnas,

    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze,
    s.seq_scan AS escaneos_secuenciales,
    s.idx_scan AS escaneos_indice,

    CASE
        WHEN s.n_dead_tup = 0 THEN 'OK'
        WHEN s.n_dead_tup < 10000 THEN 'REVISAR'
        ELSE 'VACUUM RECOMENDADO'
    END AS estado_postgres

FROM pg_stat_user_tables s
WHERE s.schemaname = 'raw_cygnus'
  AND s.relname IN (
      'clientes_proyectos',
      'interacciones',
      'clientes',
      'procesos',
      'proformas',
      'unidades'
  )
ORDER BY s.n_live_tup DESC;
