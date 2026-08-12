WITH x AS (
 SELECT codigo_proforma,codigo_unidad,
 min(fecha_inicio) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS primera_sep,
 min(fecha_inicio) FILTER (WHERE nombre='Venta' AND fecha_inicio IS NOT NULL) AS primera_venta
 FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Venta') GROUP BY codigo_proforma,codigo_unidad)
SELECT * FROM x WHERE primera_venta IS NOT NULL AND primera_sep IS NOT NULL AND primera_venta<primera_sep ORDER BY primera_venta LIMIT 500;

WITH x AS (
 SELECT codigo_proforma,codigo_unidad,
 min(fecha_inicio) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS primera_sep,
 min(fecha_inicio) FILTER (WHERE nombre='Anulacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS primera_anulacion
 FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Anulacion') GROUP BY codigo_proforma,codigo_unidad)
SELECT * FROM x WHERE primera_anulacion IS NOT NULL AND (primera_sep IS NULL OR primera_anulacion<primera_sep) ORDER BY primera_anulacion LIMIT 500;

SELECT codigo_proforma,codigo_unidad,
 count(*) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS separaciones_validas,
 count(*) FILTER (WHERE nombre='Anulacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS anulaciones_validas
FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Anulacion')
GROUP BY codigo_proforma,codigo_unidad
HAVING count(*) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita')=1
AND count(*) FILTER (WHERE nombre='Anulacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita')>1
ORDER BY anulaciones_validas DESC LIMIT 500;
