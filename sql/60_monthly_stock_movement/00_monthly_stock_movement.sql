-- Monthly stock movement export for Medallio DW.
--
-- Self-contained reporting layer over the governed event ledger.
-- It deliberately does NOT require the materialized unit-semantics / stock
-- facts to exist locally. This keeps the exporter runnable on Medallio
-- installations where Phase B exists but Phase C / v1.1 has not been installed.
--
-- Contract preserved:
--   * primary absorption scope = DEPARTAMENTO only;
--   * historical stock remains observed from analytics.fact_movimientos_stock;
--   * no current-state flag is back-cast to fabricate historical stock;
--   * only transition_applied=true events affect the report;
--   * current-stock certification/coverage, when available, is added by Python
--     as optional evidence and never required to calculate the ledger history.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.v_stock_movimiento_mensual_export AS
WITH typed_events AS (
    SELECT
        m.fecha_evento AS fecha,
        m.codigo_proyecto,
        m.codigo_unidad,
        m.tipo_evento,
        m.delta_stock,
        lower(coalesce(u.tipo_unidad, '')) AS tipo_norm
    FROM analytics.fact_movimientos_stock m
    JOIN core.dim_unidad u
      ON u.codigo_unidad = m.codigo_unidad
    WHERE m.transition_applied
      AND m.codigo_proyecto IS NOT NULL
      AND lower(coalesce(u.tipo_unidad, '')) LIKE '%departamento%'
), project_bounds AS (
    SELECT
        codigo_proyecto,
        min(fecha) AS min_fecha,
        greatest(max(fecha), current_date) AS max_fecha
    FROM typed_events
    GROUP BY codigo_proyecto
), calendar AS (
    SELECT
        b.codigo_proyecto,
        gs::date AS fecha
    FROM project_bounds b
    CROSS JOIN LATERAL generate_series(
        b.min_fecha::timestamp,
        b.max_fecha::timestamp,
        interval '1 day'
    ) gs
), daily_move AS (
    SELECT
        e.codigo_proyecto,
        e.fecha,
        count(*) FILTER (WHERE e.tipo_evento = 'ALTA_STOCK')::bigint AS altas,
        count(*) FILTER (WHERE e.tipo_evento = 'SEPARACION')::bigint AS separaciones,
        count(*) FILTER (WHERE e.tipo_evento = 'CAIDA')::bigint AS caidas,
        count(*) FILTER (WHERE e.tipo_evento = 'VENTA')::bigint AS ventas,
        coalesce(sum(e.delta_stock), 0)::bigint AS delta_stock
    FROM typed_events e
    GROUP BY e.codigo_proyecto, e.fecha
), daily AS (
    SELECT
        c.fecha,
        c.codigo_proyecto,
        coalesce(m.altas, 0)::bigint AS altas,
        coalesce(m.separaciones, 0)::bigint AS separaciones,
        coalesce(m.caidas, 0)::bigint AS caidas,
        coalesce(m.ventas, 0)::bigint AS ventas,
        coalesce(m.delta_stock, 0)::bigint AS delta_stock
    FROM calendar c
    LEFT JOIN daily_move m
      ON m.codigo_proyecto = c.codigo_proyecto
     AND m.fecha = c.fecha
), running AS (
    SELECT
        d.*,
        sum(d.delta_stock) OVER (
            PARTITION BY d.codigo_proyecto
            ORDER BY d.fecha
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint AS stock_fin_observado
    FROM daily d
), daily_stock AS (
    SELECT
        r.*,
        (r.stock_fin_observado - r.delta_stock)::bigint AS stock_inicio_observado
    FROM running r
), monthly AS (
    SELECT
        date_trunc('month', fecha)::date AS periodo_mes,
        codigo_proyecto,
        min(fecha) AS primera_fecha_observada,
        max(fecha) AS ultima_fecha_observada,
        (array_agg(stock_inicio_observado ORDER BY fecha))[1]::bigint AS stock_inicio_observado,
        (array_agg(stock_fin_observado ORDER BY fecha DESC))[1]::bigint AS saldo_final_observado,
        sum(altas)::bigint AS altas_mes,
        sum(separaciones)::bigint AS separaciones_brutas_mes,
        sum(caidas)::bigint AS caidas_mes,
        sum(separaciones - caidas)::bigint AS movimiento_neto_mes,
        sum(ventas)::bigint AS ventas_minutas_mes
    FROM daily_stock
    GROUP BY date_trunc('month', fecha)::date, codigo_proyecto
), enriched AS (
    SELECT
        m.*,
        m.separaciones_brutas_mes::numeric / nullif(m.stock_inicio_observado, 0) AS absorcion_bruta_mes,
        m.movimiento_neto_mes::numeric / nullif(m.stock_inicio_observado, 0) AS absorcion_neta_mes,
        sum(m.movimiento_neto_mes) OVER (
            PARTITION BY m.codigo_proyecto
            ORDER BY m.periodo_mes
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        )::numeric AS movimiento_neto_6m,
        first_value(m.stock_inicio_observado) OVER (
            PARTITION BY m.codigo_proyecto
            ORDER BY m.periodo_mes
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        )::numeric AS stock_inicio_ventana_6m,
        count(*) OVER (
            PARTITION BY m.codigo_proyecto
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
    'DEPARTAMENTO'::text AS tipo_unidad_consolidado,
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
    'HISTORICO_LEDGER_OBSERVADO'::text AS calidad_stock_historico,
    'FACT_MOVIMIENTOS_STOCK'::text AS metodo_stock_historico,
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
     ) > 0;

COMMENT ON VIEW analytics.v_stock_movimiento_mensual_export IS
'Resumen mensual de departamentos derivado directamente del ledger efectivo fact_movimientos_stock. No requiere reconstruir ni materializar Phase C y no fabrica stock historico faltante.';

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
    JOIN core.dim_unidad u
      ON u.codigo_unidad = m.codigo_unidad
    WHERE m.transition_applied
      AND lower(coalesce(u.tipo_unidad, '')) LIKE '%departamento%'
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
        translate(
            upper(coalesce(p.nombre_proyecto, u.nombre_proyecto_origen, '')),
            'ÁÉÍÓÚÜÑ',
            'AEIOUUN'
        ) AS proyecto_norm,
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
'Detalle mensual de movimientos efectivos de departamentos. Precios de lista/descuento son actuales; precio_venta_actual queda disponible para auditoria.';
