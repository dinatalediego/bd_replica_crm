-- ============================================================
-- MEDALLIO DW - DICCIONARIO DE COLUMNAS
-- Ayuda a localizar posibles PK, claves de negocio y watermarks.
-- Nota: las etiquetas son sugerencias heurísticas, no reemplazan
-- la validación real de unicidad.
-- ============================================================

SELECT
    table_name AS tabla,
    ordinal_position AS posicion,
    column_name AS columna,
    data_type AS tipo_dato,
    character_maximum_length AS longitud,
    numeric_precision,
    numeric_scale,
    is_nullable AS permite_null,
    column_default AS valor_default,

    CASE
        WHEN LOWER(column_name) IN ('id', 'pk') THEN 'POSIBLE PK'
        WHEN LOWER(column_name) LIKE '%_id' THEN 'POSIBLE KEY'
        WHEN LOWER(column_name) LIKE 'id_%' THEN 'POSIBLE KEY'
        WHEN LOWER(column_name) LIKE '%codigo%' THEN 'POSIBLE KEY'
        WHEN LOWER(column_name) LIKE '%documento%' THEN 'POSIBLE KEY'
        WHEN LOWER(column_name) LIKE '%fecha_actualizacion%' THEN 'WATERMARK'
        WHEN LOWER(column_name) LIKE '%updated%' THEN 'WATERMARK'
        WHEN LOWER(column_name) LIKE '%modified%' THEN 'WATERMARK'
        WHEN LOWER(column_name) LIKE '%fecha%' THEN 'FECHA'
        ELSE ''
    END AS posible_uso

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
ORDER BY table_name, ordinal_position;
