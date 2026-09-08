-- Semantic correction for a legacy Phase C field name.
--
-- `conversion_sep_venta_30d` is calculated as ventas_30d / separaciones_30d
-- using two independent rolling-window flows. It is NOT a cohort conversion
-- rate and can legitimately exceed 1 when sales/minutes in the window come
-- from separations that occurred before the same window.
--
-- Keep the physical legacy column for compatibility, but govern the business
-- label as a ratio until a true cohort conversion metric is implemented.

INSERT INTO analytics.metric_definitions(
    metric_name,business_definition,numerator_definition,
    denominator_definition,version,valid_from,is_active
)
VALUES
(
    'ratio_minutas_separaciones_departamentos_30d_observado',
    'Ratio de minutas/ventas canónicas observadas en la ventana móvil de 30 días sobre separaciones físicas efectivas de departamentos observadas en la misma ventana. Es un ratio de flujos y puede superar 100%; no es conversión de cohorte.',
    'ventas_30d where tipo_unidad_consolidado=DEPARTAMENTO',
    'separaciones_brutas_30d where tipo_unidad_consolidado=DEPARTAMENTO',
    '1.1',
    DATE '2026-08-28',
    true
)
ON CONFLICT (metric_name) DO UPDATE
SET
    business_definition=EXCLUDED.business_definition,
    numerator_definition=EXCLUDED.numerator_definition,
    denominator_definition=EXCLUDED.denominator_definition,
    version=EXCLUDED.version,
    valid_from=EXCLUDED.valid_from,
    is_active=true;

COMMENT ON COLUMN analytics.fact_absorcion_proyecto_tipo_diario.conversion_sep_venta_30d IS
'LEGACY NAME. This is ventas_30d / separaciones_brutas_30d for the same rolling window; it is a flow ratio, not cohort conversion. Business-facing label: ratio_minutas_separaciones_30d.';
