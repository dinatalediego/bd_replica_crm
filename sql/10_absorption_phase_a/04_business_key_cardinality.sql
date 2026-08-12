-- Revisar EXPLAIN antes si el equipo está limitado
SELECT nombre,count(*) AS total,count(*) FILTER (WHERE codigo_proforma IS NULL) AS proforma_null,count(*) FILTER (WHERE codigo_unidad IS NULL) AS unidad_null,count(*) FILTER (WHERE codigo_proforma IS NULL OR codigo_unidad IS NULL) AS any_key_null
FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Venta','Anulacion') GROUP BY nombre ORDER BY nombre;

SELECT codigo_proforma,count(DISTINCT codigo_unidad) AS unidades_distintas,count(*) AS eventos
FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Venta','Anulacion')
GROUP BY codigo_proforma HAVING count(DISTINCT codigo_unidad)>1 ORDER BY unidades_distintas DESC,eventos DESC LIMIT 200;

SELECT codigo_proforma,codigo_unidad,
 count(*) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS separaciones_validas,
 min(fecha_inicio) FILTER (WHERE nombre='Separacion') AS primera_sep,
 max(fecha_inicio) FILTER (WHERE nombre='Separacion') AS ultima_sep
FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Venta','Anulacion')
GROUP BY codigo_proforma,codigo_unidad
HAVING count(*) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita')>1
ORDER BY separaciones_validas DESC,ultima_sep DESC LIMIT 500;

SELECT id,count(*) AS rows FROM raw_cygnus.procesos GROUP BY id HAVING count(*)>1 LIMIT 100;
