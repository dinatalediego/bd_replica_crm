-- Evidencia local previa/posterior a reparación.

SELECT
    count(*) AS filas,
    count(DISTINCT id) AS ids_distintos,
    count(DISTINCT (nombre,id)) AS nombre_id_distintos
FROM raw_cygnus.procesos;

-- Debe devolver 0 filas.
SELECT
    nombre,
    id,
    count(*) AS veces
FROM raw_cygnus.procesos
GROUP BY nombre,id
HAVING count(*) > 1
ORDER BY veces DESC
LIMIT 100;

-- Distribución por evento.
SELECT
    nombre,
    count(*) AS filas,
    count(DISTINCT id) AS ids_distintos,
    count(*) - count(DISTINCT id) AS duplicados_dentro_nombre
FROM raw_cygnus.procesos
GROUP BY nombre
ORDER BY filas DESC;
