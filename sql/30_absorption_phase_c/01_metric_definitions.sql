CREATE TABLE IF NOT EXISTS analytics.metric_definitions (
    metric_name text PRIMARY KEY,
    business_definition text NOT NULL,
    numerator_definition text,
    denominator_definition text,
    version text NOT NULL,
    valid_from date NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO analytics.metric_definitions(
    metric_name,business_definition,numerator_definition,
    denominator_definition,version,valid_from,is_active
)
VALUES
(
    'absorcion_bruta_30d',
    'Separaciones físicas efectivas de los últimos 30 días divididas entre stock disponible al inicio de la ventana.',
    'separaciones_brutas_30d',
    'stock_inicio_ventana_30d',
    '1.0',
    DATE '2026-01-01',
    true
),
(
    'absorcion_neta_30d',
    'Separaciones físicas efectivas menos caídas/reingresos efectivos en 30 días, dividido entre stock disponible al inicio de la ventana.',
    'separaciones_netas_30d',
    'stock_inicio_ventana_30d',
    '1.0',
    DATE '2026-01-01',
    true
),
(
    'meses_stock_ventas_30d',
    'Stock disponible actual dividido entre ventas canónicas observadas durante los últimos 30 días.',
    'stock_fin',
    'ventas_30d',
    '1.0',
    DATE '2026-01-01',
    true
)
ON CONFLICT (metric_name) DO UPDATE
SET
    business_definition=EXCLUDED.business_definition,
    numerator_definition=EXCLUDED.numerator_definition,
    denominator_definition=EXCLUDED.denominator_definition,
    version=EXCLUDED.version,
    is_active=true;
