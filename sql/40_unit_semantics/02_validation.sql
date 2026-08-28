-- 0. Proyectos fuera del universo de stock / absorción.
SELECT *
FROM analytics.v_proyectos_fuera_stock
ORDER BY proyecto_id;

-- 1. Cobertura de clasificación de tipo SOLO para unidades elegibles de stock.
SELECT
    tipo_unidad_consolidado,
    count(*) AS unidades
FROM analytics.v_unidades_stock_elegibles
GROUP BY tipo_unidad_consolidado
ORDER BY unidades DESC;

-- 2. Cobertura de estado actual SOLO para unidades elegibles de stock.
SELECT
    estado_comercial_consolidado,
    orden_estado,
    count(*) AS unidades
FROM analytics.v_unidades_stock_elegibles
GROUP BY estado_comercial_consolidado,orden_estado
ORDER BY orden_estado;

-- 3. Tipos origen elegibles que todavía caen en OTRO.
-- Debe devolver 0 filas una vez excluidos contenedores no-stock como Campañas.
SELECT
    tipo_unidad_origen,
    count(*) AS unidades
FROM analytics.v_unidades_stock_elegibles
WHERE flag_otro_tipo
GROUP BY tipo_unidad_origen
ORDER BY unidades DESC,tipo_unidad_origen;

-- 4. Estados origen elegibles que todavía caen en OTRO.
SELECT
    estado_inventario_canonico,
    estado_comercial_origen,
    estado_personalizado_origen,
    count(*) AS unidades
FROM analytics.v_unidades_stock_elegibles
WHERE flag_otro_estado
GROUP BY estado_inventario_canonico,estado_comercial_origen,estado_personalizado_origen
ORDER BY unidades DESC;

-- 5. Reconciliación: el total por tipo debe reconstruir el ledger efectivo
-- únicamente para proyectos con gestión de stock.
-- Debe devolver 0 filas.
WITH ledger AS (
    SELECT
        date_trunc('month',m.fecha_evento)::date AS periodo_mes,
        m.codigo_proyecto,
        count(*) FILTER (WHERE m.tipo_evento='SEPARACION' AND m.transition_applied) AS separaciones,
        count(*) FILTER (WHERE m.tipo_evento='CAIDA' AND m.transition_applied) AS caidas,
        count(*) FILTER (WHERE m.tipo_evento='VENTA' AND m.transition_applied) AS ventas
    FROM analytics.fact_movimientos_stock m
    JOIN analytics.dim_proyecto_semantica p
      ON p.codigo_proyecto=m.codigo_proyecto
     AND p.flag_gestion_stock
    WHERE m.codigo_proyecto IS NOT NULL
    GROUP BY 1,2
), typed AS (
    SELECT
        date_trunc('month',s.fecha)::date AS periodo_mes,
        s.codigo_proyecto,
        sum(s.separaciones) AS separaciones,
        sum(s.caidas_reingresadas) AS caidas,
        sum(s.ventas) AS ventas
    FROM analytics.fact_stock_ofertado_diario_tipo s
    GROUP BY 1,2
)
SELECT
    coalesce(l.periodo_mes,t.periodo_mes) AS periodo_mes,
    coalesce(l.codigo_proyecto,t.codigo_proyecto) AS codigo_proyecto,
    coalesce(l.separaciones,0) AS sep_ledger,
    coalesce(t.separaciones,0) AS sep_por_tipo,
    coalesce(t.separaciones,0)-coalesce(l.separaciones,0) AS gap_sep,
    coalesce(l.caidas,0) AS caidas_ledger,
    coalesce(t.caidas,0) AS caidas_por_tipo,
    coalesce(t.caidas,0)-coalesce(l.caidas,0) AS gap_caidas,
    coalesce(l.ventas,0) AS ventas_ledger,
    coalesce(t.ventas,0) AS ventas_por_tipo,
    coalesce(t.ventas,0)-coalesce(l.ventas,0) AS gap_ventas
FROM ledger l
FULL OUTER JOIN typed t USING(periodo_mes,codigo_proyecto)
WHERE coalesce(t.separaciones,0)<>coalesce(l.separaciones,0)
   OR coalesce(t.caidas,0)<>coalesce(l.caidas,0)
   OR coalesce(t.ventas,0)<>coalesce(l.ventas,0)
ORDER BY periodo_mes DESC,codigo_proyecto;

-- 6. Agosto 2026: composición de eventos por producto.
SELECT
    codigo_proyecto,
    tipo_unidad_consolidado,
    sum(separaciones) AS separaciones,
    sum(caidas_reingresadas) AS caidas,
    sum(ventas) AS ventas_ledger
FROM analytics.fact_stock_ofertado_diario_tipo
WHERE fecha >= DATE '2026-08-01'
  AND fecha <  DATE '2026-09-01'
GROUP BY codigo_proyecto,tipo_unidad_consolidado
HAVING sum(separaciones)<>0 OR sum(caidas_reingresadas)<>0 OR sum(ventas)<>0
ORDER BY codigo_proyecto,tipo_unidad_consolidado;

-- 7. Contrato principal: departamentos solamente.
SELECT
    codigo_proyecto,
    sum(separaciones) AS separaciones_departamentos,
    sum(caidas_reingresadas) AS caidas_departamentos,
    sum(ventas) AS ventas_ledger_departamentos
FROM analytics.fact_stock_ofertado_diario_tipo
WHERE fecha >= DATE '2026-08-01'
  AND fecha <  DATE '2026-09-01'
  AND tipo_unidad_consolidado='DEPARTAMENTO'
GROUP BY codigo_proyecto
ORDER BY codigo_proyecto;

-- 8. Gate de completitud del snapshot actual para el UNIVERSO ELEGIBLE DE STOCK.
-- Campañas (id=24) se conserva en CORE pero no entra al denominador.
-- Debe dar gap_unidades = 0.
WITH eligible_core AS (
    SELECT count(*)::bigint AS n
    FROM core.dim_unidad u
    JOIN analytics.dim_proyecto_semantica p
      ON p.codigo_proyecto=u.codigo_proyecto
    WHERE p.flag_gestion_stock
), snap_count AS (
    SELECT count(*)::bigint AS n
    FROM analytics.fact_stock_snapshot_diario_unidad
    WHERE fecha_snapshot=(
        SELECT max(fecha_snapshot)
        FROM analytics.fact_stock_snapshot_diario_unidad
    )
)
SELECT
    c.n AS unidades_core_elegibles,
    s.n AS unidades_snapshot,
    s.n-c.n AS gap_unidades
FROM eligible_core c CROSS JOIN snap_count s;

-- 9. Reconciliación estado actual completo vs ledger observado.
-- Los gaps NO se fuerzan a cero: muestran cobertura histórica faltante.
SELECT *
FROM analytics.v_stock_coverage_actual_por_tipo
WHERE gap_stock_disponible<>0
   OR gap_separadas<>0
   OR gap_vendidas<>0
ORDER BY
    abs(gap_stock_disponible) DESC,
    codigo_proyecto,
    tipo_unidad_consolidado;

-- 10. Resumen ejecutivo de cobertura actual, ya sin proyectos no-stock.
SELECT
    sum(stock_disponible_actual)::bigint AS stock_disponible_actual,
    sum(stock_disponible_ledger)::bigint AS stock_disponible_ledger,
    sum(gap_stock_disponible)::bigint AS gap_stock_disponible,
    sum(separadas_actual)::bigint AS separadas_actual,
    sum(separadas_ledger)::bigint AS separadas_ledger,
    sum(gap_separadas)::bigint AS gap_separadas,
    sum(vendidas_actual)::bigint AS vendidas_actual,
    sum(vendidas_ledger)::bigint AS vendidas_ledger,
    sum(gap_vendidas)::bigint AS gap_vendidas
FROM analytics.v_stock_coverage_actual_por_tipo;

-- 11. Calidad de absorción principal actual por proyecto.
SELECT
    codigo_proyecto,
    fecha,
    stock_fin AS stock_fin_ledger_absorcion,
    stock_disponible_actual,
    gap_stock_disponible,
    cobertura_stock_disponible_ratio,
    calidad_stock,
    absorcion_bruta_30d,
    absorcion_neta_30d
FROM analytics.v_absorcion_principal_estado_actual
ORDER BY
    ledger_reconcilia_estado_actual,
    abs(gap_stock_disponible) DESC,
    codigo_proyecto;

-- 12. Gate explícito: ningún proyecto fuera de stock debe aparecer en facts de stock/absorción.
-- Debe devolver 0 filas.
SELECT 'stock_tipo' AS objeto, s.codigo_proyecto, count(*) AS filas
FROM analytics.fact_stock_ofertado_diario_tipo s
JOIN analytics.dim_proyecto_semantica p USING(codigo_proyecto)
WHERE NOT p.flag_gestion_stock
GROUP BY s.codigo_proyecto
UNION ALL
SELECT 'absorcion_tipo', a.codigo_proyecto, count(*)
FROM analytics.fact_absorcion_proyecto_tipo_diario a
JOIN analytics.dim_proyecto_semantica p USING(codigo_proyecto)
WHERE NOT p.flag_absorcion
GROUP BY a.codigo_proyecto
UNION ALL
SELECT 'snapshot_actual', s.codigo_proyecto, count(*)
FROM analytics.fact_stock_snapshot_diario_unidad s
JOIN analytics.dim_proyecto_semantica p USING(codigo_proyecto)
WHERE NOT p.flag_gestion_stock
  AND s.fecha_snapshot=(SELECT max(fecha_snapshot) FROM analytics.fact_stock_snapshot_diario_unidad)
GROUP BY s.codigo_proyecto;
