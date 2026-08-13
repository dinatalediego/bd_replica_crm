-- 1. Tamaños
SELECT 'int_unidad_entrada_stock' tabla, count(*) filas
FROM analytics.int_unidad_entrada_stock
UNION ALL
SELECT 'int_proforma_minuta', count(*)
FROM analytics.int_proforma_minuta
UNION ALL
SELECT 'int_ciclo_comercial_unidad', count(*)
FROM analytics.int_ciclo_comercial_unidad
UNION ALL
SELECT 'fact_movimientos_stock', count(*)
FROM analytics.fact_movimientos_stock;

-- 2. Ajustes de fecha
SELECT
    count(*) AS ciclos,
    count(*) FILTER (WHERE fecha_separacion_ajustada) AS fechas_ajustadas,
    round(
        100.0 * count(*) FILTER (WHERE fecha_separacion_ajustada)
        / nullif(count(*),0), 2
    ) AS pct_ajustadas
FROM analytics.int_ciclo_comercial_unidad;

-- 3. Método fecha venta
SELECT
    metodo_fecha_venta,
    count(*) AS ciclos
FROM analytics.int_ciclo_comercial_unidad
GROUP BY metodo_fecha_venta
ORDER BY ciclos DESC;

-- 4. Resultado ciclo
SELECT
    resultado_ciclo,
    count(*) AS ciclos
FROM analytics.int_ciclo_comercial_unidad
GROUP BY resultado_ciclo
ORDER BY ciclos DESC;

-- 5. Movimientos efectivos / auditables
SELECT
    tipo_evento,
    transition_applied,
    count(*) AS eventos,
    sum(delta_stock) AS delta_stock,
    sum(delta_ventas) AS delta_ventas,
    sum(delta_caidas) AS delta_caidas
FROM analytics.fact_movimientos_stock
GROUP BY tipo_evento, transition_applied
ORDER BY tipo_evento, transition_applied DESC;

-- 6. QA
SELECT *
FROM observability.absorption_quality_results
ORDER BY checked_at DESC, quality_result_id DESC
LIMIT 100;

-- 7. Regla fundamental: una unidad no puede tener más reingresos efectivos
-- que separaciones efectivas.
SELECT
    codigo_unidad,
    count(*) FILTER (
        WHERE tipo_evento='SEPARACION' AND transition_applied
    ) sep_efectivas,
    count(*) FILTER (
        WHERE tipo_evento='CAIDA' AND transition_applied
    ) caidas_efectivas
FROM analytics.fact_movimientos_stock
GROUP BY codigo_unidad
HAVING count(*) FILTER (
        WHERE tipo_evento='CAIDA' AND transition_applied
    ) > count(*) FILTER (
        WHERE tipo_evento='SEPARACION' AND transition_applied
    )
LIMIT 100;
