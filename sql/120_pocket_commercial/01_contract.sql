-- Medallio Pocket: real commercial aggregate at project x month grain.
-- Source is the certified/observed monthly stock movement layer.
-- No client-, lead-, unit-, proforma-, phone-, email- or free-text CRM fields cross this contract.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.v_pocket_commercial_project_month AS
SELECT
    m.periodo_mes,
    m.codigo_proyecto,
    m.proyecto AS nombre_proyecto,
    m.primera_fecha_observada,
    m.ultima_fecha_observada,
    m.stock_inicio_observado AS stock_inicial,
    m.altas_mes,
    m.separaciones_brutas_mes,
    m.caidas_mes,
    m.movimiento_neto_mes AS separaciones_netas_mes,
    m.ventas_minutas_mes,
    m.saldo_final_observado AS stock_final,
    m.absorcion_bruta_mes,
    m.absorcion_neta_mes,
    m.absorcion_neta_6m,
    m.stock_disponible_actual,
    m.cobertura_stock_disponible_ratio,
    m.ledger_reconcilia_estado_actual,
    m.calidad_stock_historico,
    m.metodo_stock_historico,
    m.metodo_movimiento,
    m.metodo_venta,
    (m.periodo_mes = date_trunc('month', (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date)::date) AS mes_parcial,
    (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date AS fecha_corte
FROM analytics.v_stock_movimiento_mensual_export m
WHERE m.tipo_unidad_consolidado = 'DEPARTAMENTO';

COMMENT ON VIEW analytics.v_pocket_commercial_project_month IS
'Contrato sanitizado proyecto x mes para Medallio Pocket. Fuente observada: stock, separaciones, caidas, minutas/ventas y absorcion de departamentos. Sin PII ni granularidad CRM.';

CREATE OR REPLACE VIEW analytics.v_pocket_project_summary_current AS
WITH ranked AS (
    SELECT
        p.*,
        row_number() OVER (
            PARTITION BY p.codigo_proyecto
            ORDER BY p.periodo_mes DESC, p.ultima_fecha_observada DESC
        ) AS rn
    FROM analytics.v_pocket_commercial_project_month p
)
SELECT
    codigo_proyecto,
    nombre_proyecto,
    periodo_mes,
    fecha_corte,
    mes_parcial,
    ultima_fecha_observada,
    stock_inicial,
    separaciones_brutas_mes,
    caidas_mes,
    separaciones_netas_mes,
    ventas_minutas_mes,
    stock_final,
    absorcion_bruta_mes,
    absorcion_neta_mes,
    absorcion_neta_6m,
    stock_disponible_actual,
    cobertura_stock_disponible_ratio,
    ledger_reconcilia_estado_actual,
    calidad_stock_historico
FROM ranked
WHERE rn = 1;

COMMENT ON VIEW analytics.v_pocket_project_summary_current IS
'Ultimo corte real por proyecto para Medallio Pocket. No infiere ventas desde cambios de stock.';

-- Fail-fast audit: this view must remain aggregate-only.
CREATE OR REPLACE VIEW analytics.v_pocket_commercial_privacy_audit AS
SELECT
    c.table_schema,
    c.table_name,
    c.column_name
FROM information_schema.columns c
WHERE c.table_schema = 'analytics'
  AND c.table_name IN ('v_pocket_commercial_project_month', 'v_pocket_project_summary_current')
  AND lower(c.column_name) ~ '(cliente|client|lead|dni|document|telefono|phone|celular|correo|email|direccion|address|nota|note|coment|conversation|grabacion|recording|proforma|unidad|asesor)';

COMMENT ON VIEW analytics.v_pocket_commercial_privacy_audit IS
'Debe devolver cero filas. Detecta nombres de columnas incompatibles con la frontera movil sanitizada.';
