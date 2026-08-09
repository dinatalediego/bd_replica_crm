-- ============================================================
-- MEDALLIO DW - PK / UNIQUE / FOREIGN KEYS DECLARADAS
-- Muestra constraints reales de PostgreSQL.
-- ============================================================

SELECT
    tc.table_schema AS esquema,
    tc.table_name AS tabla,
    tc.constraint_type AS tipo_constraint,
    tc.constraint_name,
    kcu.column_name AS columna,
    kcu.ordinal_position AS posicion
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
   AND tc.table_name = kcu.table_name
WHERE tc.table_schema = 'raw_cygnus'
  AND tc.table_name IN (
      'clientes_proyectos',
      'interacciones',
      'clientes',
      'procesos',
      'proformas',
      'unidades'
  )
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
ORDER BY
    tc.table_name,
    tc.constraint_type,
    kcu.ordinal_position;
