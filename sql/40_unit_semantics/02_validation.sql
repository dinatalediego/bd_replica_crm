-- 1. Cobertura de clasificación de tipo.
SELECT
    tipo_unidad_consolidado,
    count(*) AS unidades
FROM analytics.dim_unidad_semantica
GROUP BY tipo_unidad_consolidado
ORDER BY unidades DESC;

-- 2. Cobertura de estado actual.
SELECT
    estado_comercial_consolidado,
    orden_estado,
    count(*) AS unidades
FROM analytics.dim_unidad_semantica
GROUP BY estado_comercial_consolidado,orden_estado
ORDER BY orden_estado;

-- 3. Tipos origen que todavía caen en OTRO.
SELECT
    tipo_unidad_origen,
    count(*) AS unidades
FROM analytics.dim_unidad_semantica
WHERE flag_otro_tipo
GROUP BY tipo_unidad_origen
ORDER BY unidades DESC,tipo_unidad_origen;

-- 4. Estados origen que todavía caen en OTRO.
SELECT
    estado_inventario_canonico,
    estado_comercial_origen,
    estado_personalizado_origen,
    count(*) AS unidades
FROM analytics.dim_unidad_semantica
WHERE flag_otro_estado
GROUP BY estado_inventario_canonico,estado_comercial_origen,estado_personalizado_origen
ORDER BY unidades DESC;

-- 5. Reconciliación: el total por tipo debe reconstruir el ledger efectivo.
WITH ledger AS (
    SELECT
        date_trunc('month',m.fecha_evento)::date AS periodo_mes,
        m.codigo_proyecto,
        count(*) FILTER (WHERE m.tipo_evento='SEPARACION' AND m.transition_applied) AS separaciones,
        count(*) FILTER (WHERE m.tipo_evento='CAIDA' AND m.transition_applied) AS caidas,
        count(*) FILTER (WHERE m.tipo_evento='VENTA' AND m.transition_applied) AS ventas
    FROM analytics.fact_movimientos_stock m
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

-- 6. Agosto 2026: composición que explicó la brecha observada.
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
