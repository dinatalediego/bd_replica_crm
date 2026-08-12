WITH eventos AS (
 SELECT id AS source_id,codigo_proforma,codigo_unidad,nombre,estado,nombre_flujo,fecha_inicio,
 row_number() OVER (PARTITION BY codigo_proforma,codigo_unidad ORDER BY fecha_inicio NULLS LAST,id) AS event_seq,
 lag(nombre) OVER (PARTITION BY codigo_proforma,codigo_unidad ORDER BY fecha_inicio NULLS LAST,id) AS prev_event,
 lag(fecha_inicio) OVER (PARTITION BY codigo_proforma,codigo_unidad ORDER BY fecha_inicio NULLS LAST,id) AS prev_event_at
 FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Venta','Anulacion'))
SELECT * FROM eventos ORDER BY codigo_proforma,codigo_unidad,event_seq LIMIT 2000;

WITH ciclos AS (
 SELECT codigo_proforma,codigo_unidad,
 count(*) FILTER (WHERE nombre='Separacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS separaciones,
 count(*) FILTER (WHERE nombre='Anulacion' AND fecha_inicio IS NOT NULL AND coalesce(nombre_flujo,'')<>'Desistimiento de visita') AS anulaciones
 FROM raw_cygnus.procesos WHERE codigo_proforma IS NOT NULL AND codigo_unidad IS NOT NULL AND nombre IN ('Separacion','Venta','Anulacion') GROUP BY codigo_proforma,codigo_unidad)
SELECT * FROM ciclos WHERE separaciones>=1 AND anulaciones>1 ORDER BY anulaciones DESC,separaciones DESC LIMIT 500;
