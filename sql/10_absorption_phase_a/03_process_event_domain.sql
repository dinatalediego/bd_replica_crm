-- Ejecutar si metadata confirma columnas: nombre, estado, nombre_flujo, fecha_inicio
SELECT nombre,count(*) AS rows FROM raw_cygnus.procesos GROUP BY nombre ORDER BY rows DESC;
SELECT nombre,estado,count(*) AS rows FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Venta','Anulacion') GROUP BY nombre,estado ORDER BY nombre,rows DESC;
SELECT nombre,nombre_flujo,count(*) AS rows FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Venta','Anulacion') GROUP BY nombre,nombre_flujo ORDER BY nombre,rows DESC LIMIT 300;
SELECT nombre,count(*) AS total_rows,count(*) FILTER (WHERE fecha_inicio IS NULL) AS fecha_inicio_null,min(fecha_inicio),max(fecha_inicio) FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Venta','Anulacion') GROUP BY nombre ORDER BY nombre;
SELECT nombre,count(*) AS rows_desistimiento FROM raw_cygnus.procesos WHERE nombre IN ('Separacion','Anulacion') AND nombre_flujo='Desistimiento de visita' GROUP BY nombre;
