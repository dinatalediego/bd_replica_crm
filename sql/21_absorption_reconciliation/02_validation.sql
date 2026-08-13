-- Resumen ejecutivo.
SELECT *
FROM observability.v_absorption_reconciliation_current;

-- Matriz documental vs inventario.
SELECT
    resultado_ciclo AS resultado_documental,
    resultado_inventario,
    count(*) AS ciclos
FROM analytics.v_ciclo_comercial_reconciliado
GROUP BY resultado_ciclo,resultado_inventario
ORDER BY resultado_ciclo,resultado_inventario;

-- Resultado canónico.
SELECT
    resultado_canonico,
    reconciliation_status,
    confidence_level,
    count(*) AS ciclos
FROM analytics.v_ciclo_comercial_reconciliado
GROUP BY resultado_canonico,reconciliation_status,confidence_level
ORDER BY ciclos DESC;

-- Excepciones.
SELECT
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    fecha_separacion,
    fecha_venta_documental,
    fecha_venta_validada,
    primera_fecha_caida,
    resultado_ciclo AS resultado_documental,
    resultado_inventario,
    resultado_canonico,
    reconciliation_status,
    eventos_no_efectivos
FROM analytics.v_ciclo_comercial_reconciliado
WHERE requiere_revision
ORDER BY
    CASE reconciliation_status
        WHEN 'ERROR_TEMPORAL' THEN 1
        WHEN 'OPEN_BUSINESS_RULE' THEN 2
        ELSE 3
    END,
    codigo_proyecto,
    codigo_unidad;

-- Estado físico actual.
SELECT
    current_inventory_state,
    count(*) AS unidades,
    sum(available_stock_balance) AS available_balance,
    sum(separated_active_balance) AS separated_balance,
    sum(effective_sales) AS effective_sales
FROM analytics.v_inventory_state_current
GROUP BY current_inventory_state
ORDER BY current_inventory_state;
