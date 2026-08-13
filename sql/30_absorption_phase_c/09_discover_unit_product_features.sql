-- Discovery para Fase C v0.2: no inventar nombres.
SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema='raw_cygnus'
  AND table_name='unidades'
  AND (
      lower(column_name) LIKE '%tipolog%'
      OR lower(column_name) LIKE '%subdiv%'
      OR lower(column_name) LIKE '%dorm%'
      OR lower(column_name) LIKE '%piso%'
      OR lower(column_name) LIKE '%tipo%unidad%'
      OR lower(column_name) LIKE '%area%'
      OR lower(column_name) LIKE '%precio%'
      OR lower(column_name) LIKE '%descuento%'
  )
ORDER BY ordinal_position;

-- Cardinalidad de candidatos: ejecutar después de identificar los nombres físicos.
-- No se genera SQL dinámico de negocio hasta validar semántica point-in-time.
