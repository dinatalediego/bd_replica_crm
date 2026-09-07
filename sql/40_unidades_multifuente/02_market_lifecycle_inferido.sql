-- Analítica de mercado inferida a partir del snapshot actual de raw_mercado.unidades.
--
-- Importante:
-- * raw_mercado no tiene hoy el mismo ledger transaccional que raw_cygnus.
-- * Por ello NO se inventan ventas, caídas ni reingresos.
-- * La fecha de inicio comercial de cada proyecto se aproxima como
--   MIN(fecha_separacion) - 1 mes, según la regla operativa acordada.
-- * Cada unidad se considera ofertada desde ese inicio inferido hasta su
--   fecha_separacion; si no tiene fecha_separacion, permanece en stock hasta hoy.
-- * Estas métricas deben identificarse como INFERIDAS, no observadas.

CREATE SCHEMA IF NOT EXISTS analytics_market;

CREATE OR REPLACE VIEW analytics_market.v_unidad_lifecycle_inferido AS
WITH proyecto_inicio AS (
    SELECT
        codigo_proyecto,
        min(fecha_separacion)::date AS primera_fecha_separacion,
        (min(fecha_separacion)::date - interval '1 month')::date AS fecha_inicio_comercial_inferida
    FROM raw_mercado.unidades
    WHERE codigo_proyecto IS NOT NULL
      AND fecha_separacion IS NOT NULL
    GROUP BY codigo_proyecto
)
SELECT
    'raw_mercado'::text AS esquema_fuente,
    ('raw_mercado:' || u.codigo::text) AS unidad_fuente_key,
    u.codigo::text AS codigo_unidad,
    u.codigo_proyecto::text AS codigo_proyecto,
    u.nombre_proyecto::text AS nombre_proyecto,
    u.nombre_tipologia::text AS nombre_tipologia,
    u.total_habitaciones::numeric AS total_habitaciones,
    u.area_total::numeric AS area_total,
    u.estado_comercial::text AS estado_comercial_actual,
    u.precio_lista::numeric AS precio_lista,
    u.precio_venta::numeric AS precio_venta,
    u.precio_m2::numeric AS precio_m2,
    p.primera_fecha_separacion,
    p.fecha_inicio_comercial_inferida,
    u.fecha_separacion::date AS fecha_salida_stock_inferida,
    CASE
        WHEN u.fecha_separacion IS NOT NULL THEN 'SEPARACION'
        ELSE NULL
    END::text AS tipo_salida_inferida,
    CASE
        WHEN u.fecha_separacion IS NULL THEN true
        ELSE false
    END AS sigue_en_stock_inferido,
    'PRIMERA_SEPARACION_PROYECTO_MENOS_1_MES'::text AS metodo_inicio_comercial,
    'FECHA_SEPARACION_UNIDAD'::text AS metodo_salida_stock,
    'INFERIDO_DESDE_SNAPSHOT'::text AS nivel_evidencia,
    u._etl_loaded_at AS source_loaded_at,
    u._etl_source_run_id AS source_run_id
FROM raw_mercado.unidades u
LEFT JOIN proyecto_inicio p USING (codigo_proyecto);

COMMENT ON VIEW analytics_market.v_unidad_lifecycle_inferido IS
'Ciclo de inventario de mercado inferido desde snapshot: entrada = primera separación del proyecto menos 1 mes; salida = fecha_separacion de la unidad.';

CREATE OR REPLACE VIEW analytics_market.v_movimientos_inventario_inferidos AS
SELECT
    md5(unidad_fuente_key || '|ALTA_STOCK|' || fecha_inicio_comercial_inferida::text) AS movimiento_key,
    esquema_fuente,
    unidad_fuente_key,
    codigo_unidad,
    codigo_proyecto,
    nombre_proyecto,
    nombre_tipologia,
    total_habitaciones,
    fecha_inicio_comercial_inferida AS fecha_evento,
    'ALTA_STOCK'::text AS tipo_evento,
    1::integer AS delta_stock,
    0::integer AS delta_separaciones,
    nivel_evidencia,
    metodo_inicio_comercial AS metodo_inferencia
FROM analytics_market.v_unidad_lifecycle_inferido
WHERE fecha_inicio_comercial_inferida IS NOT NULL

UNION ALL

SELECT
    md5(unidad_fuente_key || '|SEPARACION|' || fecha_salida_stock_inferida::text) AS movimiento_key,
    esquema_fuente,
    unidad_fuente_key,
    codigo_unidad,
    codigo_proyecto,
    nombre_proyecto,
    nombre_tipologia,
    total_habitaciones,
    fecha_salida_stock_inferida AS fecha_evento,
    'SEPARACION'::text AS tipo_evento,
    -1::integer AS delta_stock,
    1::integer AS delta_separaciones,
    nivel_evidencia,
    metodo_salida_stock AS metodo_inferencia
FROM analytics_market.v_unidad_lifecycle_inferido
WHERE fecha_salida_stock_inferida IS NOT NULL;

COMMENT ON VIEW analytics_market.v_movimientos_inventario_inferidos IS
'Ledger mínimo inferido del mercado. Solo modela ALTA_STOCK y SEPARACION porque son los eventos recuperables con evidencia disponible.';

CREATE OR REPLACE VIEW analytics_market.v_stock_proyecto_diario_inferido AS
WITH bounds AS (
    SELECT
        codigo_proyecto,
        min(fecha_evento) AS min_fecha
    FROM analytics_market.v_movimientos_inventario_inferidos
    WHERE codigo_proyecto IS NOT NULL
    GROUP BY codigo_proyecto
),
calendar AS (
    SELECT
        b.codigo_proyecto,
        gs::date AS fecha
    FROM bounds b
    CROSS JOIN LATERAL generate_series(
        b.min_fecha::timestamp,
        current_date::timestamp,
        interval '1 day'
    ) gs
),
daily AS (
    SELECT
        codigo_proyecto,
        fecha_evento AS fecha,
        count(*) FILTER (WHERE tipo_evento = 'ALTA_STOCK')::bigint AS altas,
        count(*) FILTER (WHERE tipo_evento = 'SEPARACION')::bigint AS separaciones,
        coalesce(sum(delta_stock), 0)::bigint AS delta_stock
    FROM analytics_market.v_movimientos_inventario_inferidos
    GROUP BY codigo_proyecto, fecha_evento
),
running AS (
    SELECT
        c.fecha,
        c.codigo_proyecto,
        coalesce(d.altas, 0)::bigint AS altas,
        coalesce(d.separaciones, 0)::bigint AS separaciones,
        coalesce(d.delta_stock, 0)::bigint AS delta_stock,
        sum(coalesce(d.delta_stock, 0)) OVER (
            PARTITION BY c.codigo_proyecto
            ORDER BY c.fecha
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint AS stock_fin
    FROM calendar c
    LEFT JOIN daily d
      ON d.codigo_proyecto = c.codigo_proyecto
     AND d.fecha = c.fecha
)
SELECT
    'raw_mercado'::text AS esquema_fuente,
    fecha,
    codigo_proyecto,
    (stock_fin - delta_stock)::bigint AS stock_inicio,
    altas,
    separaciones,
    0::bigint AS caidas_reingresadas,
    0::bigint AS ventas,
    delta_stock,
    stock_fin,
    'INFERIDO_DESDE_SNAPSHOT'::text AS nivel_evidencia
FROM running;

COMMENT ON VIEW analytics_market.v_stock_proyecto_diario_inferido IS
'Stock diario de mercado inferido; no equivale al ledger observado de Cygnus.';

CREATE OR REPLACE VIEW analytics_market.v_absorcion_proyecto_diario_inferida AS
WITH b AS (
    SELECT
        s.*,
        sum(separaciones) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )::bigint AS separaciones_7d,
        lag(stock_fin, 7) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
        )::bigint AS stock_inicio_ventana_7d,
        sum(separaciones) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )::bigint AS separaciones_30d,
        lag(stock_fin, 30) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
        )::bigint AS stock_inicio_ventana_30d,
        sum(separaciones) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
            ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
        )::bigint AS separaciones_90d,
        lag(stock_fin, 90) OVER (
            PARTITION BY codigo_proyecto ORDER BY fecha
        )::bigint AS stock_inicio_ventana_90d
    FROM analytics_market.v_stock_proyecto_diario_inferido s
)
SELECT
    esquema_fuente,
    fecha,
    codigo_proyecto,
    stock_inicio,
    stock_fin,
    (stock_inicio + stock_fin)::numeric / 2 AS stock_promedio,
    separaciones AS separaciones_brutas,
    0::bigint AS caidas,
    separaciones AS separaciones_netas,
    0::bigint AS ventas,
    separaciones_7d AS separaciones_brutas_7d,
    separaciones_7d AS separaciones_netas_7d,
    stock_inicio_ventana_7d,
    separaciones_7d::numeric / nullif(stock_inicio_ventana_7d, 0) AS absorcion_bruta_7d,
    separaciones_7d::numeric / nullif(stock_inicio_ventana_7d, 0) AS absorcion_neta_7d,
    separaciones_30d AS separaciones_brutas_30d,
    separaciones_30d AS separaciones_netas_30d,
    stock_inicio_ventana_30d,
    separaciones_30d::numeric / nullif(stock_inicio_ventana_30d, 0) AS absorcion_bruta_30d,
    separaciones_30d::numeric / nullif(stock_inicio_ventana_30d, 0) AS absorcion_neta_30d,
    separaciones_90d AS separaciones_brutas_90d,
    separaciones_90d AS separaciones_netas_90d,
    stock_inicio_ventana_90d,
    separaciones_90d::numeric / nullif(stock_inicio_ventana_90d, 0) AS absorcion_bruta_90d,
    separaciones_90d::numeric / nullif(stock_inicio_ventana_90d, 0) AS absorcion_neta_90d,
    nivel_evidencia,
    'SEPARACIONES_SOBRE_STOCK_INICIAL_VENTANA'::text AS metodo_absorcion
FROM b;

COMMENT ON VIEW analytics_market.v_absorcion_proyecto_diario_inferida IS
'Absorción 7/30/90d de mercado inferida desde fechas de separación y stock reconstruido.';
