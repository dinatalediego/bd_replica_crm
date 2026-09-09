-- Monthly stock movement export for Medallio DW.
--
-- Contract:
--   * Primary business absorption scope = DEPARTAMENTO only.
--   * Historical movement/absorption remains event-ledger observed evidence.
--   * Current stock certification remains analytics.fact_stock_snapshot_diario_unidad.
--   * Never back-cast current-state flags to fabricate historical stock.
--
-- This layer is presentation-ready but keeps quality/provenance explicit.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.v_stock_movimiento_mensual_export AS
WITH daily AS (
    SELECT
        s.fecha,
        date_trunc('month', s.fecha)::date AS periodo_mes,
        s.codigo_proyecto,
        s.tipo_unidad_consolidado,
        s.stock_inicio,
        s.stock_fin,
        s.altas,
        s.separaciones,
        s.caidas_reingresadas,
        s.ventas
    FROM analytics.fact_stock_ofertado_diario_tipo s
    WHERE s.tipo_unidad_consolidado = 'DEPARTAMENTO'
), monthly AS (
    SELECT
        periodo_mes,
        codigo_proyecto,
        tipo_unidad_consolidado,
        min(fecha) AS primera_fecha_observada,
        max(fecha) AS ultima_fecha_observada,
        (array_agg(stock_inicio ORDER BY fecha))[1]::bigint AS stock_inicio_observado,
        (array_agg(stock_fin ORDER BY fecha DESC))[1]::bigint AS saldo_final_observado,
        sum(altas)::bigint AS altas_mes,
        sum(separaciones)::bigint AS separaciones_brutas_mes,
        sum(caidas_reingresadas)::bigint AS caidas_mes,
        sum(separaciones - caidas_reingresadas)::bigint AS movimiento_neto_mes,
        sum(ventas)::bigint AS ventas_minutas_mes
    FROM daily
    GROUP BY periodo_mes, codigo_proyecto, tipo_unidad_consolidado
), enriched AS (
    SELECT
        m.*,
        m.separaciones_brutas_mes::numeric / nullif(m.stock_inicio_observado, 0) AS absorcion_bruta_mes,
        m.movimiento_neto_mes::numeric / nullif(m.stock_inicio_observado, 0) AS absorcion_neta_mes,
        sum(m.movimiento_neto_mes) OVER (
            PARTITION BY m.codigo_proyecto, m.tipo_unidad_consolidado
            ORDER BY m.periodo_mes
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        )::numeric AS movimiento_neto_6m,
        first_value(m.stock_inicio_observado) OVER (
            PARTITION BY m.codigo_proyecto, m.tipo_unidad_consolidado
            ORDER BY m.periodo_mes
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        )::numeric AS stock_inicio_ventana_6m,
        count(*) OVER (
            PARTITION BY m.codigo_proyecto, m.tipo_unidad_consolidado
            ORDER BY m.periodo_mes
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ) AS meses_en_ventana_6m
    FROM monthly m
), active_rules AS (
    SELECT *
    FROM analytics.stock_discount_rules
    WHERE active
      AND valid_from <= CURRENT_DATE
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
)
SELECT
    e.periodo_mes,
    e.codigo_proyecto,
    coalesce(r.project_display_name, p.nombre_proyecto, e.codigo_proyecto) AS proyecto,
    e.tipo_unidad_consolidado,
    e.primera_fecha_observada,
    e.ultima_fecha_observada,
    e.stock_inicio_observado,
    e.altas_mes,
    e.separaciones_brutas_mes,
    e.caidas_mes,
    e.movimiento_neto_mes,
    e.ventas_minutas_mes,
    e.saldo_final_observado,
    e.absorcion_bruta_mes,
    e.absorcion_neta_mes,
    CASE
        WHEN e.meses_en_ventana_6m = 6
        THEN e.movimiento_neto_6m / nullif(e.stock_inicio_ventana_6m, 0)
        ELSE NULL
    END AS absorcion_neta_6m,
    e.meses_en_ventana_6m,
    c.stock_disponible_actual,
    c.stock_disponible_ledger,
    c.gap_stock_disponible,
    c.cobertura_stock_disponible_ratio,
    c.ledger_reconcilia_estado_actual,
    CASE
        WHEN c.ledger_reconcilia_estado_actual THEN 'CERTIFICADO_ESTADO_ACTUAL'
        ELSE 'HISTORICO_LEDGER_CON_GAP_DE_COBERTURA'
    END AS calidad_stock_historico,
    'OBSERVADO_LEDGER'::text AS metodo_stock_historico,
    'SEPARACIONES_EFECTIVAS_MENOS_CAIDAS'::text AS metodo_movimiento,
    'VENTA_EFECTIVA / MINUTA_CANONICA'::text AS metodo_venta
FROM enriched e
LEFT JOIN core.dim_proyecto p
  ON p.codigo_proyecto = e.codigo_proyecto
LEFT JOIN active_rules r
  ON position(
        r.project_key in translate(
            upper(coalesce(p.nombre_proyecto, e.codigo_proyecto, '')),
            'ÁÉÍÓÚÜÑ',
            'AEIOUUN'
        )
     ) > 0
LEFT JOIN analytics.v_stock_coverage_actual_por_tipo c
  ON c.codigo_proyecto = e.codigo_proyecto
 AND c.tipo_unidad_consolidado = e.tipo_unidad_consolidado;

COMMENT ON VIEW analytics.v_stock_movimiento_mensual_export IS
'Resumen mensual de stock y absorcion principal de departamentos. Historico observado desde fact_movimientos_stock/fact_stock_ofertado_diario_tipo; no fabrica stock historico faltante.';

CREATE OR REPLACE VIEW analytics.v_stock_movimiento_mensual_unidad_export AS
WITH events AS (
    SELECT
        date_trunc('month', m.fecha_evento)::date AS periodo_mes,
        m.codigo_proyecto,
        m.codigo_unidad,
        m.codigo_proforma,
        m.fecha_evento,
        m.tipo_evento,
        m.source_table,
        m.source_id,
        m.transition_reason,
        row_number() OVER (
            PARTITION BY date_trunc('month', m.fecha_evento)::date,
                         m.codigo_proyecto,
                         m.codigo_unidad,
                         m.tipo_evento
            ORDER BY m.fecha_evento, m.event_order, m.movement_id
        ) AS event_rank
    FROM analytics.fact_movimientos_stock m
    JOIN analytics.dim_unidad_semantica s
      ON s.codigo_unidad = m.codigo_unidad
    WHERE m.transition_applied
      AND s.tipo_unidad_consolidado = 'DEPARTAMENTO'
      AND m.tipo_evento IN ('SEPARACION', 'CAIDA', 'VENTA')
), rules AS (
    SELECT *
    FROM analytics.stock_discount_rules
    WHERE active
      AND valid_from <= CURRENT_DATE
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
), unit_current AS (
    SELECT
        u.codigo_unidad,
        u.codigo_proyecto,
        u.tipo_unidad,
        u.piso,
        u.area_total,
        u.estado_comercial,
        u.precio_lista_actual,
        u.precio_venta_actual,
        coalesce(u.moneda_precio_lista, 'PEN') AS moneda,
        translate(upper(coalesce(p.nombre_proyecto, u.nombre_proyecto_origen, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS proyecto_norm,
        coalesce(p.nombre_proyecto, u.nombre_proyecto_origen, u.codigo_proyecto) AS proyecto_origen
    FROM core.dim_unidad u
    LEFT JOIN core.dim_proyecto p
      ON p.codigo_proyecto = u.codigo_proyecto
)
SELECT
    e.periodo_mes,
    e.codigo_proyecto,
    coalesce(r.project_display_name, u.proyecto_origen) AS proyecto,
    e.codigo_unidad AS unidad,
    u.tipo_unidad,
    u.piso,
    u.area_total,
    e.tipo_evento AS movimiento,
    e.fecha_evento,
    e.codigo_proforma,
    u.estado_comercial AS estado_actual,
    u.precio_lista_actual AS precio_lista,
    coalesce(r.discount_pct, 0::numeric) AS discount_pct,
    CASE
        WHEN u.precio_lista_actual IS NULL THEN NULL
        ELSE round(u.precio_lista_actual * (1 - coalesce(r.discount_pct, 0::numeric)), 2)
    END AS precio_con_descuento,
    u.precio_venta_actual,
    u.moneda,
    e.source_table,
    e.source_id,
    e.transition_reason,
    e.event_rank
FROM events e
JOIN unit_current u
  ON u.codigo_unidad = e.codigo_unidad
LEFT JOIN rules r
  ON position(r.project_key in u.proyecto_norm) > 0;

COMMENT ON VIEW analytics.v_stock_movimiento_mensual_unidad_export IS
'Detalle de departamentos con movimientos comerciales efectivos por mes. Precios de lista/descuento corresponden al estado actual de core.dim_unidad y reglas vigentes; precio_venta_actual queda para auditoria.';
