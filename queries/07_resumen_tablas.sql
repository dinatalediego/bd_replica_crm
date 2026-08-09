-- ============================================================
-- MEDALLIO DW - RESUMEN RAPIDO
-- Consulta liviana para abrir diariamente en DBeaver.
-- ============================================================

SELECT
    s.relname AS tabla,
    s.n_live_tup AS filas_estimadas,
    pg_size_pretty(
        pg_total_relation_size(
            quote_ident(s.schemaname) || '.' || quote_ident(s.relname)
        )
    ) AS tamano_total,
    (
        SELECT COUNT(*)
        FROM information_schema.columns c
        WHERE c.table_schema = s.schemaname
          AND c.table_name = s.relname
    ) AS columnas,
    s.last_autoanalyze AS ultimo_autoanalyze,
    s.last_analyze AS ultimo_analyze
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
ORDER BY s.relname;
