CREATE OR REPLACE PROCEDURE analytics.refresh_unit_semantics_absorption_v11()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE TABLE
        analytics.fact_absorcion_proyecto_tipo_diario,
        analytics.fact_stock_ofertado_diario_tipo,
        analytics.dim_unidad_semantica;

    -------------------------------------------------------------------------
    -- 1. Semantic unit dimension.
    -- Type semantics are derived from core.dim_unidad.
    -- Current commercial state prioritizes canonical inventory state and
    -- only falls back to source commercial labels when needed.
    -------------------------------------------------------------------------
    INSERT INTO analytics.dim_unidad_semantica(
        codigo_unidad,codigo_proyecto,tipo_unidad_origen,tipo_unidad_consolidado,
        flag_departamento,flag_estacionamiento,flag_deposito,flag_local,flag_otro_tipo,
        estado_comercial_origen,estado_personalizado_origen,estado_inventario_canonico,
        estado_comercial_consolidado,
        flag_disponible,flag_bloqueado,flag_estado_separado,flag_vendido,flag_otro_estado,
        orden_estado
    )
    WITH base AS (
        SELECT
            u.codigo_unidad,
            u.codigo_proyecto,
            u.tipo_unidad,
            u.estado_comercial,
            u.estado_personalizado,
            i.current_inventory_state,
            lower(coalesce(u.tipo_unidad,'')) AS tipo_norm,
            lower(coalesce(u.estado_comercial,'')) AS estado_norm,
            lower(coalesce(u.estado_personalizado,'')) AS estado_personalizado_norm
        FROM core.dim_unidad u
        LEFT JOIN analytics.v_inventory_state_current i
          ON i.codigo_unidad=u.codigo_unidad
    ), typed AS (
        SELECT
            b.*,
            CASE
                WHEN tipo_norm LIKE '%departamento%' THEN 'DEPARTAMENTO'
                WHEN tipo_norm LIKE '%estacionamiento%' OR tipo_norm LIKE '%parking%' THEN 'ESTACIONAMIENTO'
                WHEN tipo_norm LIKE '%depósito%' OR tipo_norm LIKE '%deposito%' THEN 'DEPOSITO'
                WHEN tipo_norm LIKE '%local%' THEN 'LOCAL'
                ELSE 'OTRO'
            END AS tipo_consolidado
        FROM base b
    ), stated AS (
        SELECT
            t.*,
            CASE
                WHEN current_inventory_state='SOLD' THEN 'VENDIDO'
                WHEN current_inventory_state='SEPARATED' THEN 'SEPARADO'
                -- BLOCKED is a current commercial restriction not represented
                -- by the inventory ledger, so it may refine AVAILABLE.
                WHEN estado_norm LIKE '%bloque%'
                  OR estado_personalizado_norm LIKE '%bloque%'
                    THEN 'BLOQUEADO'
                WHEN current_inventory_state='AVAILABLE' THEN 'DISPONIBLE'
                WHEN estado_norm LIKE '%vendid%'
                  OR estado_personalizado_norm LIKE '%vendid%'
                    THEN 'VENDIDO'
                WHEN estado_norm LIKE '%separad%'
                  OR estado_personalizado_norm LIKE '%separad%'
                    THEN 'SEPARADO'
                WHEN estado_norm LIKE '%dispon%'
                  OR estado_personalizado_norm LIKE '%dispon%'
                    THEN 'DISPONIBLE'
                ELSE 'OTRO'
            END AS estado_consolidado
        FROM typed t
    )
    SELECT
        codigo_unidad,
        codigo_proyecto,
        tipo_unidad,
        tipo_consolidado,
        tipo_consolidado='DEPARTAMENTO',
        tipo_consolidado='ESTACIONAMIENTO',
        tipo_consolidado='DEPOSITO',
        tipo_consolidado='LOCAL',
        tipo_consolidado='OTRO',
        estado_comercial,
        estado_personalizado,
        current_inventory_state,
        estado_consolidado,
        estado_consolidado='DISPONIBLE',
        estado_consolidado='BLOQUEADO',
        estado_consolidado='SEPARADO',
        estado_consolidado='VENDIDO',
        estado_consolidado='OTRO',
        CASE estado_consolidado
            WHEN 'DISPONIBLE' THEN 1
            WHEN 'BLOQUEADO'  THEN 2
            WHEN 'SEPARADO'   THEN 3
            WHEN 'VENDIDO'    THEN 4
            ELSE 99
        END
    FROM stated;

    -------------------------------------------------------------------------
    -- 2. Daily stock by project + governed unit type.
    -- History is still event-sourced from fact_movimientos_stock.
    -------------------------------------------------------------------------
    WITH project_type_bounds AS (
        SELECT
            m.codigo_proyecto,
            s.tipo_unidad_consolidado,
            min(m.fecha_evento) AS min_fecha,
            greatest(max(m.fecha_evento),current_date) AS max_fecha
        FROM analytics.fact_movimientos_stock m
        JOIN analytics.dim_unidad_semantica s
          ON s.codigo_unidad=m.codigo_unidad
        WHERE m.codigo_proyecto IS NOT NULL
          AND m.transition_applied
        GROUP BY m.codigo_proyecto,s.tipo_unidad_consolidado
    ), calendar AS (
        SELECT
            b.codigo_proyecto,
            b.tipo_unidad_consolidado,
            gs::date AS fecha
        FROM project_type_bounds b
        CROSS JOIN LATERAL generate_series(
            b.min_fecha::timestamp,
            b.max_fecha::timestamp,
            interval '1 day'
        ) gs
    ), daily_move AS (
        SELECT
            m.codigo_proyecto,
            s.tipo_unidad_consolidado,
            m.fecha_evento AS fecha,
            count(*) FILTER (WHERE m.tipo_evento='ALTA_STOCK' AND m.transition_applied) AS altas,
            count(*) FILTER (WHERE m.tipo_evento='SEPARACION' AND m.transition_applied) AS separaciones,
            count(*) FILTER (WHERE m.tipo_evento='CAIDA' AND m.transition_applied) AS caidas,
            count(*) FILTER (WHERE m.tipo_evento='VENTA' AND m.transition_applied) AS ventas,
            sum(m.delta_stock) FILTER (WHERE m.transition_applied) AS delta_stock,
            sum(m.delta_separadas_activas) FILTER (WHERE m.transition_applied) AS delta_separadas,
            sum(m.delta_ventas) FILTER (WHERE m.transition_applied) AS delta_ventas
        FROM analytics.fact_movimientos_stock m
        JOIN analytics.dim_unidad_semantica s
          ON s.codigo_unidad=m.codigo_unidad
        WHERE m.codigo_proyecto IS NOT NULL
        GROUP BY m.codigo_proyecto,s.tipo_unidad_consolidado,m.fecha_evento
    ), x AS (
        SELECT
            cal.fecha,
            cal.codigo_proyecto,
            cal.tipo_unidad_consolidado,
            coalesce(m.altas,0)::bigint AS altas,
            coalesce(m.separaciones,0)::bigint AS separaciones,
            coalesce(m.caidas,0)::bigint AS caidas,
            coalesce(m.ventas,0)::bigint AS ventas,
            coalesce(m.delta_stock,0)::bigint AS delta_stock,
            coalesce(m.delta_separadas,0)::bigint AS delta_separadas,
            coalesce(m.delta_ventas,0)::bigint AS delta_ventas
        FROM calendar cal
        LEFT JOIN daily_move m
          ON m.codigo_proyecto=cal.codigo_proyecto
         AND m.tipo_unidad_consolidado=cal.tipo_unidad_consolidado
         AND m.fecha=cal.fecha
    ), running AS (
        SELECT
            x.*,
            sum(delta_stock) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS stock_fin,
            sum(delta_separadas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS separadas_activas,
            sum(delta_ventas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS vendidas_acumuladas
        FROM x
    )
    INSERT INTO analytics.fact_stock_ofertado_diario_tipo(
        fecha,codigo_proyecto,tipo_unidad_consolidado,
        stock_inicio,altas,separaciones,caidas_reingresadas,retiros,ventas,
        delta_stock,stock_fin,separadas_activas,vendidas_acumuladas
    )
    SELECT
        fecha,codigo_proyecto,tipo_unidad_consolidado,
        (stock_fin-delta_stock)::bigint,
        altas,separaciones,caidas,0,ventas,
        delta_stock,stock_fin,separadas_activas,vendidas_acumuladas
    FROM running;

    -------------------------------------------------------------------------
    -- 3. Absorption by project + unit type.
    -- This preserves a consolidated stock table while making absorption scope
    -- explicit and non-mixed.
    -------------------------------------------------------------------------
    WITH b AS (
        SELECT
            s.*,
            sum(separaciones) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS sep_7d,
            sum(caidas_reingresadas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS caida_7d,
            sum(ventas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS ventas_7d,
            lag(stock_fin,7) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado ORDER BY fecha
            ) AS stock_start_7d,

            sum(separaciones) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS sep_30d,
            sum(caidas_reingresadas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS caida_30d,
            sum(ventas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS ventas_30d,
            lag(stock_fin,30) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado ORDER BY fecha
            ) AS stock_start_30d,

            sum(separaciones) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS sep_90d,
            sum(caidas_reingresadas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS caida_90d,
            sum(ventas) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado
                ORDER BY fecha ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS ventas_90d,
            lag(stock_fin,90) OVER (
                PARTITION BY codigo_proyecto,tipo_unidad_consolidado ORDER BY fecha
            ) AS stock_start_90d
        FROM analytics.fact_stock_ofertado_diario_tipo s
    )
    INSERT INTO analytics.fact_absorcion_proyecto_tipo_diario(
        fecha,codigo_proyecto,tipo_unidad_consolidado,
        stock_inicio,stock_fin,stock_promedio,
        separaciones_brutas,caidas,separaciones_netas,ventas,
        separaciones_brutas_7d,caidas_7d,separaciones_netas_7d,ventas_7d,
        stock_inicio_ventana_7d,absorcion_bruta_7d,absorcion_neta_7d,
        separaciones_brutas_30d,caidas_30d,separaciones_netas_30d,ventas_30d,
        stock_inicio_ventana_30d,absorcion_bruta_30d,absorcion_neta_30d,
        separaciones_brutas_90d,caidas_90d,separaciones_netas_90d,ventas_90d,
        stock_inicio_ventana_90d,absorcion_bruta_90d,absorcion_neta_90d,
        conversion_sep_venta_30d,tasa_caida_30d,
        velocidad_venta_diaria_30d,meses_stock_ventas_30d
    )
    SELECT
        fecha,codigo_proyecto,tipo_unidad_consolidado,
        stock_inicio,stock_fin,(stock_inicio+stock_fin)::numeric/2,
        separaciones,caidas_reingresadas,separaciones-caidas_reingresadas,ventas,

        sep_7d,caida_7d,sep_7d-caida_7d,ventas_7d,
        stock_start_7d,
        sep_7d::numeric/nullif(stock_start_7d,0),
        (sep_7d-caida_7d)::numeric/nullif(stock_start_7d,0),

        sep_30d,caida_30d,sep_30d-caida_30d,ventas_30d,
        stock_start_30d,
        sep_30d::numeric/nullif(stock_start_30d,0),
        (sep_30d-caida_30d)::numeric/nullif(stock_start_30d,0),

        sep_90d,caida_90d,sep_90d-caida_90d,ventas_90d,
        stock_start_90d,
        sep_90d::numeric/nullif(stock_start_90d,0),
        (sep_90d-caida_90d)::numeric/nullif(stock_start_90d,0),

        ventas_30d::numeric/nullif(sep_30d,0),
        caida_30d::numeric/nullif(sep_30d,0),
        ventas_30d::numeric/30.0,
        stock_fin::numeric/nullif(ventas_30d,0)
    FROM b;
END $$;

CREATE OR REPLACE VIEW analytics.v_absorcion_departamentos_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='DEPARTAMENTO';

CREATE OR REPLACE VIEW analytics.v_absorcion_estacionamientos_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='ESTACIONAMIENTO';

CREATE OR REPLACE VIEW analytics.v_absorcion_depositos_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='DEPOSITO';

CREATE OR REPLACE VIEW analytics.v_absorcion_locales_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='LOCAL';

CREATE OR REPLACE VIEW analytics.v_absorcion_otros_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='OTRO';

CREATE OR REPLACE VIEW analytics.v_absorcion_principal_proyecto_diario AS
SELECT *
FROM analytics.fact_absorcion_proyecto_tipo_diario
WHERE tipo_unidad_consolidado='DEPARTAMENTO';

CREATE OR REPLACE VIEW analytics.v_stock_consolidado_actual_por_tipo AS
SELECT DISTINCT ON (codigo_proyecto,tipo_unidad_consolidado)
    codigo_proyecto,
    tipo_unidad_consolidado,
    fecha,
    stock_fin,
    separadas_activas,
    vendidas_acumuladas
FROM analytics.fact_stock_ofertado_diario_tipo
ORDER BY codigo_proyecto,tipo_unidad_consolidado,fecha DESC;
