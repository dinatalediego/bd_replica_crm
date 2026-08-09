-- ============================================================
-- MEDALLIO DW - COLUMNAS FECHA/TIMESTAMP CANDIDATAS A WATERMARK
-- Paso 1: lista columnas temporales.
-- Luego puedes probar MAX(columna) en cada tabla.
-- ============================================================

SELECT
    table_name AS tabla,
    column_name AS columna_fecha,
    data_type AS tipo_dato
FROM information_schema.columns
WHERE table_schema = 'raw_cygnus'
  AND table_name IN (
      'clientes_proyectos',
      'interacciones',
      'clientes',
      'procesos',
      'proformas',
      'unidades'
  )
  AND data_type IN (
      'date',
      'timestamp without time zone',
      'timestamp with time zone'
  )
ORDER BY table_name, ordinal_position;
