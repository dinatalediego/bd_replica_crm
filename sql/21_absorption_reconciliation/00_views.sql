CREATE OR REPLACE VIEW analytics.v_inventory_state_current AS
WITH last_event AS (
    SELECT DISTINCT ON (codigo_unidad)
        codigo_unidad,
        codigo_proyecto,
        fecha_evento AS last_event_date,
        tipo_evento AS last_event_type,
        estado_nuevo AS current_inventory_state,
        event_order,
        transition_applied
    FROM analytics.fact_movimientos_stock
    ORDER BY codigo_unidad, event_order DESC
),
agg AS (
    SELECT
        codigo_unidad,
        max(codigo_proyecto) AS codigo_proyecto,
        sum(delta_stock) AS available_stock_balance,
        sum(delta_separadas_activas) AS separated_active_balance,
        sum(delta_ventas) AS effective_sales,
        sum(delta_caidas) AS effective_cancellations,
        count(*) FILTER (
            WHERE tipo_evento='SEPARACION' AND transition_applied
        ) AS effective_separations,
        count(*) FILTER (
            WHERE transition_applied=false
        ) AS non_effective_events
    FROM analytics.fact_movimientos_stock
    GROUP BY codigo_unidad
)
SELECT
    a.codigo_unidad,
    coalesce(l.codigo_proyecto,a.codigo_proyecto) AS codigo_proyecto,
    l.current_inventory_state,
    l.last_event_date,
    l.last_event_type,
    a.available_stock_balance,
    a.separated_active_balance,
    a.effective_separations,
    a.effective_sales,
    a.effective_cancellations,
    a.non_effective_events
FROM agg a
LEFT JOIN last_event l USING (codigo_unidad);


CREATE OR REPLACE VIEW analytics.v_ciclo_comercial_reconciliado AS
WITH ledger_cycle AS (
    SELECT
        codigo_proforma,
        codigo_unidad,

        bool_or(
            tipo_evento='SEPARACION'
            AND transition_applied
        ) AS separacion_efectiva,

        bool_or(
            tipo_evento='VENTA'
            AND transition_applied
        ) AS venta_efectiva,

        bool_or(
            tipo_evento='CAIDA'
            AND transition_applied
        ) AS caida_efectiva,

        min(fecha_evento) FILTER (
            WHERE tipo_evento='SEPARACION'
              AND transition_applied
        ) AS fecha_separacion_efectiva,

        min(fecha_evento) FILTER (
            WHERE tipo_evento='VENTA'
              AND transition_applied
        ) AS fecha_venta_efectiva,

        min(fecha_evento) FILTER (
            WHERE tipo_evento='CAIDA'
              AND transition_applied
        ) AS fecha_caida_efectiva,

        count(*) FILTER (
            WHERE transition_applied=false
        ) AS eventos_no_efectivos
    FROM analytics.fact_movimientos_stock
    WHERE codigo_proforma IS NOT NULL
    GROUP BY codigo_proforma,codigo_unidad
),
base AS (
    SELECT
        c.*,
        coalesce(l.separacion_efectiva,false) AS separacion_efectiva_inventario,
        coalesce(l.venta_efectiva,false) AS venta_efectiva_inventario,
        coalesce(l.caida_efectiva,false) AS caida_efectiva_inventario,
        l.fecha_separacion_efectiva,
        l.fecha_venta_efectiva,
        l.fecha_caida_efectiva,
        coalesce(l.eventos_no_efectivos,0) AS eventos_no_efectivos,

        c.fecha_venta AS fecha_venta_documental,

        CASE
            WHEN c.fecha_venta IS NULL THEN NULL
            WHEN c.fecha_venta < c.fecha_separacion THEN NULL
            ELSE c.fecha_venta
        END AS fecha_venta_validada,

        (
            c.fecha_venta IS NOT NULL
            AND c.fecha_venta < c.fecha_separacion
        ) AS fecha_venta_anterior_separacion,

        (
            c.fecha_venta IS NOT NULL
            AND c.primera_fecha_caida IS NOT NULL
            AND c.fecha_venta = c.primera_fecha_caida
        ) AS venta_caida_mismo_dia
    FROM analytics.int_ciclo_comercial_unidad c
    LEFT JOIN ledger_cycle l
      ON l.codigo_proforma=c.codigo_proforma
     AND l.codigo_unidad=c.codigo_unidad
)
SELECT
    b.*,

    CASE
        WHEN b.venta_efectiva_inventario THEN 'VENTA'
        WHEN b.caida_efectiva_inventario THEN 'CAIDA'
        WHEN b.separacion_efectiva_inventario THEN 'ABIERTA'
        ELSE 'SIN_TRANSICION'
    END AS resultado_inventario,

    CASE
        WHEN b.fecha_venta_anterior_separacion
            THEN 'FECHA_VENTA_ANTERIOR_SEPARACION'

        WHEN b.venta_caida_mismo_dia
            THEN 'AMBIGUO_VENTA_CAIDA_MISMO_DIA'

        WHEN b.venta_efectiva_inventario
            THEN 'VENTA'

        WHEN b.caida_efectiva_inventario
            THEN 'CAIDA'

        WHEN b.separacion_efectiva_inventario
            THEN 'ABIERTA'

        WHEN b.resultado_ciclo='VENTA'
            THEN 'VENTA_DOCUMENTAL_SIN_TRANSICION_INVENTARIO'

        WHEN b.resultado_ciclo='CAIDA'
            THEN 'CAIDA_DOCUMENTAL_SIN_REINGRESO_INVENTARIO'

        WHEN b.resultado_ciclo='ABIERTA'
            THEN 'ABIERTA_SIN_TRANSICION_INVENTARIO'

        ELSE 'SIN_CLASIFICAR'
    END AS resultado_canonico,

    CASE
        WHEN b.fecha_venta_anterior_separacion
            THEN 'ERROR_TEMPORAL'
        WHEN b.venta_caida_mismo_dia
            THEN 'OPEN_BUSINESS_RULE'
        WHEN b.resultado_ciclo =
             CASE
                WHEN b.venta_efectiva_inventario THEN 'VENTA'
                WHEN b.caida_efectiva_inventario THEN 'CAIDA'
                WHEN b.separacion_efectiva_inventario THEN 'ABIERTA'
                ELSE 'SIN_TRANSICION'
             END
            THEN 'RECONCILED'
        ELSE 'DOCUMENTAL_VS_INVENTARIO'
    END AS reconciliation_status,

    (
        b.fecha_venta_anterior_separacion
        OR b.venta_caida_mismo_dia
        OR (
            b.resultado_ciclo <>
            CASE
                WHEN b.venta_efectiva_inventario THEN 'VENTA'
                WHEN b.caida_efectiva_inventario THEN 'CAIDA'
                WHEN b.separacion_efectiva_inventario THEN 'ABIERTA'
                ELSE 'SIN_TRANSICION'
            END
        )
    ) AS requiere_revision,

    CASE
        WHEN b.fecha_venta_anterior_separacion THEN 'LOW'
        WHEN b.venta_caida_mismo_dia THEN 'LOW'
        WHEN b.venta_efectiva_inventario
          OR b.caida_efectiva_inventario
          OR b.separacion_efectiva_inventario
            THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS confidence_level

FROM base b;


CREATE OR REPLACE VIEW observability.v_absorption_reconciliation_current AS
SELECT
    count(*) AS total_cycles,

    count(*) FILTER (
        WHERE reconciliation_status='RECONCILED'
    ) AS reconciled_cycles,

    count(*) FILTER (
        WHERE reconciliation_status='DOCUMENTAL_VS_INVENTARIO'
    ) AS documental_inventory_divergence,

    count(*) FILTER (
        WHERE reconciliation_status='ERROR_TEMPORAL'
    ) AS temporal_errors,

    count(*) FILTER (
        WHERE reconciliation_status='OPEN_BUSINESS_RULE'
    ) AS open_business_rules,

    count(*) FILTER (
        WHERE requiere_revision
    ) AS cycles_requiring_review,

    round(
        100.0 * count(*) FILTER (
            WHERE reconciliation_status='RECONCILED'
        )
        / nullif(count(*),0),
        2
    ) AS reconciliation_rate_pct,

    count(*) FILTER (
        WHERE resultado_canonico='VENTA'
    ) AS canonical_sales,

    count(*) FILTER (
        WHERE resultado_canonico='CAIDA'
    ) AS canonical_cancellations,

    count(*) FILTER (
        WHERE resultado_canonico='ABIERTA'
    ) AS canonical_open_cycles,

    count(*) FILTER (
        WHERE resultado_canonico='VENTA_DOCUMENTAL_SIN_TRANSICION_INVENTARIO'
    ) AS documental_sales_without_inventory_transition,

    count(*) FILTER (
        WHERE resultado_canonico='CAIDA_DOCUMENTAL_SIN_REINGRESO_INVENTARIO'
    ) AS documental_cancellations_without_inventory_reentry

FROM analytics.v_ciclo_comercial_reconciliado;
