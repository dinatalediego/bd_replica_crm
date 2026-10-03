-- Report-scoped reconciliation adapter. Preserves the existing reconciliation
-- rules without replacing legacy views. Explicit Phase-B projection prevents
-- appended compatibility columns from changing the public column order.
CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_reconciliado AS
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
        c.codigo_proforma,
        c.codigo_unidad,
        c.codigo_proyecto,
        c.separacion_source_id,
        c.fecha_entrada_stock,
        c.fecha_separacion_raw,
        c.fecha_separacion,
        c.fecha_separacion_ajustada,
        c.venta_source_id,
        c.fecha_firma_legacy,
        c.datos_extras_fecha_minuta_id,
        c.fecha_de_minuta,
        c.fecha_venta,
        c.metodo_fecha_venta,
        c.primera_fecha_caida,
        c.ultima_fecha_caida,
        c.cantidad_anulaciones,
        c.resultado_ciclo,
        c.dias_separacion_venta,
        c.dias_separacion_caida,
        c.documento_cliente,
        c.asesor,
        c.tipo_unidad_principal,
        c.refreshed_at,
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
