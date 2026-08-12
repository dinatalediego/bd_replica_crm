-- Adaptar solo después de confirmar nombres físicos
SELECT codigo_proforma,count(*) AS rows_proforma_unidad,count(DISTINCT codigo_unidad) AS unidades_distintas
FROM raw_cygnus.proforma_unidad WHERE codigo_proforma IS NOT NULL GROUP BY codigo_proforma ORDER BY unidades_distintas DESC,rows_proforma_unidad DESC LIMIT 500;

SELECT codigo_proforma,codigo_unidad,count(*) AS rows
FROM raw_cygnus.proforma_unidad WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL
GROUP BY codigo_proforma,codigo_unidad HAVING count(*)>1 ORDER BY rows DESC LIMIT 500;

-- Si `unidades` contiene `codigo`:
-- SELECT count(*) FROM raw_cygnus.proforma_unidad pu LEFT JOIN raw_cygnus.unidades u ON u.codigo=pu.codigo_unidad WHERE pu.codigo_unidad IS NOT NULL AND u.codigo IS NULL;
-- Si `proformas` contiene `codigo`:
-- SELECT count(*) FROM raw_cygnus.proforma_unidad pu LEFT JOIN raw_cygnus.proformas p ON p.codigo=pu.codigo_proforma WHERE pu.codigo_proforma IS NOT NULL AND p.codigo IS NULL;
