-- ============================================================
-- MEDALLIO DW - INDICES DE LAS 6 TABLAS
-- ============================================================

SELECT
    schemaname AS esquema,
    tablename AS tabla,
    indexname AS indice,
    indexdef AS definicion
FROM pg_indexes
WHERE schemaname = 'raw_cygnus'
  AND tablename IN (
      'clientes_proyectos',
      'interacciones',
      'clientes',
      'procesos',
      'proformas',
      'unidades'
  )
ORDER BY tablename, indexname;
