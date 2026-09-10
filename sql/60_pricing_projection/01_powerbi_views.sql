-- Canonical/compatibility views for Power BI.
-- Derived columns live in the DW, not duplicated in input tables.

CREATE OR REPLACE VIEW analytics.v_base_proyeccion_tipologia AS
SELECT
    b.proyecto,
    b.tipo_unidad,
    b.nombre_tipologia,
    b.tipologia_ubicacion,
    b.stock_total_inicial,
    b.precio_m2_base,
    b.area_total_promedio,
    b.descuento_promedio,
    b.ventas_mes_base,
    b.meta_meses,
    b.precio_m2_base * b.area_total_promedio * (1 - b.descuento_promedio)
        AS precio_unitario_base,
    b.stock_total_inicial
        * (b.precio_m2_base * b.area_total_promedio * (1 - b.descuento_promedio))
        AS revenue_base_tipologia,
    b.proyecto || ' | ' || b.tipo_unidad || ' | ' || b.nombre_tipologia
        AS "ClaveTipologia",
    b.proyecto || ' | ' || b.tipo_unidad || ' | ' || b.nombre_tipologia
        || ' | ' || lpad(b.tipologia_ubicacion::text, 2, '0')
        AS "ClaveTipologiaUbicacion",
    b.fecha_inicio,
    b.origen_supuesto
FROM pricing.projection_baseline_assumption b
WHERE b.activo;

CREATE OR REPLACE VIEW analytics.v_supuestos_absorcion AS
SELECT
    escenario,
    tramo,
    mes_inicio,
    mes_fin,
    factor_ventas,
    origen_supuesto
FROM pricing.absorption_scenario
WHERE activo;

CREATE OR REPLACE VIEW analytics.v_hitos_pricing AS
SELECT
    h.proyecto,
    h.tipo_unidad,
    h.nombre_tipologia,
    h.hito,
    h.mes_hito,
    h.pct_vendido_objetivo,
    h.aumento_usd_m2,
    h.proyecto || ' | ' || h.tipo_unidad || ' | ' || h.nombre_tipologia
        AS "ClaveTipologia",
    h.origen_supuesto
FROM pricing.price_milestone h
WHERE h.activo;

COMMENT ON VIEW analytics.v_base_proyeccion_tipologia IS
'Compatibilidad Power BI de Base_Proyeccion_Tipologia. Los valores son supuestos controlados, no stock observado.';
COMMENT ON VIEW analytics.v_supuestos_absorcion IS
'Compatibilidad Power BI de Supuestos_Absorcion.';
COMMENT ON VIEW analytics.v_hitos_pricing IS
'Compatibilidad Power BI de Hitos_Pricing.';
