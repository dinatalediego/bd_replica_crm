-- MEDALLIO · Pricing inmobiliario study v1
-- Objetivo: crear una capa reproducible para diagnóstico, snapshots de precio
-- y reporting ejecutivo sin inventar elasticidades causales.

CREATE SCHEMA IF NOT EXISTS pricing_analytics;

CREATE TABLE IF NOT EXISTS pricing_analytics.fact_precio_unidad_diario (
    snapshot_date           date NOT NULL,
    unidad_fuente_key       text NOT NULL,
    esquema_fuente          text NOT NULL,
    codigo_unidad           text,
    codigo_proyecto         text,
    nombre_proyecto         text,
    tipo_unidad             text,
    nombre_tipologia        text,
    tipologia_ubicacion     text,
    piso                    text,
    total_habitaciones      numeric,
    area_total              numeric,
    estado_comercial        text,
    precio_lista            numeric,
    precio_base_proforma    numeric,
    descuento_venta         numeric,
    precio_venta            numeric,
    precio_m2_fuente        numeric,
    precio_m2_lista_calc    numeric,
    moneda                  text,
    source_loaded_at        timestamptz,
    captured_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, unidad_fuente_key)
);

CREATE INDEX IF NOT EXISTS ix_fact_precio_unidad_diario_proyecto_fecha
    ON pricing_analytics.fact_precio_unidad_diario (codigo_proyecto, snapshot_date);

CREATE INDEX IF NOT EXISTS ix_fact_precio_unidad_diario_unidad_fecha
    ON pricing_analytics.fact_precio_unidad_diario (codigo_unidad, snapshot_date);

CREATE OR REPLACE PROCEDURE pricing_analytics.capture_price_snapshot(
    p_snapshot_date date DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO pricing_analytics.fact_precio_unidad_diario (
        snapshot_date,
        unidad_fuente_key,
        esquema_fuente,
        codigo_unidad,
        codigo_proyecto,
        nombre_proyecto,
        tipo_unidad,
        nombre_tipologia,
        tipologia_ubicacion,
        piso,
        total_habitaciones,
        area_total,
        estado_comercial,
        precio_lista,
        precio_base_proforma,
        descuento_venta,
        precio_venta,
        precio_m2_fuente,
        precio_m2_lista_calc,
        moneda,
        source_loaded_at,
        captured_at
    )
    SELECT
        p_snapshot_date,
        u.unidad_fuente_key,
        u.esquema_fuente,
        u.codigo,
        u.codigo_proyecto,
        u.nombre_proyecto,
        u.tipo_unidad,
        u.nombre_tipologia,
        u.tipologia_ubicacion,
        u.piso,
        u.total_habitaciones,
        u.area_total,
        u.estado_comercial,
        u.precio_lista,
        u.precio_base_proforma,
        u.descuento_venta,
        u.precio_venta,
        u.precio_m2,
        CASE
            WHEN u.area_total > 0 AND u.precio_lista IS NOT NULL
                THEN round(u.precio_lista / u.area_total, 4)
            ELSE NULL
        END,
        coalesce(u.moneda_precio_lista, u.moneda_venta, 'PEN'),
        u.source_loaded_at,
        now()
    FROM core.v_unidades_fuentes u
    ON CONFLICT (snapshot_date, unidad_fuente_key) DO UPDATE
    SET
        codigo_unidad = EXCLUDED.codigo_unidad,
        codigo_proyecto = EXCLUDED.codigo_proyecto,
        nombre_proyecto = EXCLUDED.nombre_proyecto,
        tipo_unidad = EXCLUDED.tipo_unidad,
        nombre_tipologia = EXCLUDED.nombre_tipologia,
        tipologia_ubicacion = EXCLUDED.tipologia_ubicacion,
        piso = EXCLUDED.piso,
        total_habitaciones = EXCLUDED.total_habitaciones,
        area_total = EXCLUDED.area_total,
        estado_comercial = EXCLUDED.estado_comercial,
        precio_lista = EXCLUDED.precio_lista,
        precio_base_proforma = EXCLUDED.precio_base_proforma,
        descuento_venta = EXCLUDED.descuento_venta,
        precio_venta = EXCLUDED.precio_venta,
        precio_m2_fuente = EXCLUDED.precio_m2_fuente,
        precio_m2_lista_calc = EXCLUDED.precio_m2_lista_calc,
        moneda = EXCLUDED.moneda,
        source_loaded_at = EXCLUDED.source_loaded_at,
        captured_at = now();
END;
$$;

CREATE OR REPLACE VIEW pricing_analytics.v_pricing_unit_current AS
WITH ranked AS (
    SELECT
        u.*,
        translate(upper(coalesce(u.estado_comercial, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS estado_norm,
        translate(upper(coalesce(u.tipo_unidad, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS tipo_norm,
        row_number() OVER (
            PARTITION BY coalesce(u.codigo_proyecto, u.nombre_proyecto), u.codigo
            ORDER BY
                u.source_loaded_at DESC NULLS LAST,
                CASE WHEN u.esquema_fuente = 'raw_cygnus' THEN 0 ELSE 1 END
        ) AS rn
    FROM core.v_unidades_fuentes u
)
SELECT
    esquema_fuente,
    unidad_fuente_key,
    codigo AS codigo_unidad,
    codigo_proyecto,
    nombre_proyecto,
    codigo_subdivision,
    nombre_subdivision,
    CASE
        WHEN tipo_norm LIKE '%ESTACION%' THEN 'Estacionamiento'
        WHEN tipo_norm LIKE '%DEPOSITO%' THEN 'Depósito'
        WHEN tipo_norm LIKE '%LOCAL%' THEN 'Local'
        WHEN tipo_norm LIKE '%DEPART%' OR tipo_norm LIKE '%FLAT%' OR tipo_norm LIKE '%DUPLEX%' OR tipo_norm LIKE '%TRIPLEX%'
            THEN 'Departamento'
        ELSE initcap(lower(coalesce(tipo_unidad, 'Sin clasificar')))
    END AS tipo_unidad,
    piso,
    nombre_tipologia,
    tipologia_ubicacion,
    total_habitaciones,
    total_banos,
    area_libre,
    area_techada,
    area_total,
    estado_comercial,
    CASE
        WHEN estado_norm LIKE '%NO DISPON%' OR estado_norm LIKE '%BLOQUE%' THEN 'NO_DISPONIBLE'
        WHEN estado_norm LIKE '%SEPAR%' THEN 'SEPARADO'
        WHEN estado_norm LIKE '%VEND%' THEN 'VENDIDO'
        WHEN estado_norm = 'DISPONIBLE' OR estado_norm LIKE 'DISPONIBLE%' THEN 'DISPONIBLE'
        ELSE 'OTRO'
    END AS estado_bucket,
    precio_lista,
    precio_base_proforma,
    descuento_venta,
    precio_venta,
    coalesce(precio_m2, CASE WHEN area_total > 0 THEN precio_lista / area_total END) AS precio_m2_referencia,
    CASE WHEN area_total > 0 THEN precio_lista / area_total END AS precio_m2_lista,
    CASE WHEN area_total > 0 THEN precio_venta / area_total END AS precio_m2_venta,
    coalesce(moneda_precio_lista, moneda_venta, 'PEN') AS moneda,
    fecha_precio_actualizado,
    fecha_actualizacion,
    source_loaded_at,
    source_run_id
FROM ranked
WHERE rn = 1;

CREATE OR REPLACE VIEW pricing_analytics.v_pricing_unit_positioning AS
WITH base AS (
    SELECT *
    FROM pricing_analytics.v_pricing_unit_current
    WHERE tipo_unidad = 'Departamento'
      AND precio_m2_lista IS NOT NULL
      AND area_total > 0
), segment_stats AS (
    SELECT
        codigo_proyecto,
        coalesce(nullif(nombre_tipologia, ''), nullif(tipologia_ubicacion, ''), 'SIN_TIPOLOGIA') AS segmento,
        count(*) AS n_segmento,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY precio_m2_lista) AS mediana_precio_m2_segmento
    FROM base
    GROUP BY 1, 2
), project_stats AS (
    SELECT
        codigo_proyecto,
        count(*) AS n_proyecto,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY precio_m2_lista) AS mediana_precio_m2_proyecto
    FROM base
    GROUP BY 1
)
SELECT
    b.*,
    coalesce(nullif(b.nombre_tipologia, ''), nullif(b.tipologia_ubicacion, ''), 'SIN_TIPOLOGIA') AS segmento_pricing,
    s.n_segmento,
    p.n_proyecto,
    s.mediana_precio_m2_segmento,
    p.mediana_precio_m2_proyecto,
    coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto) AS benchmark_interno_precio_m2,
    CASE
        WHEN coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto) > 0
            THEN b.precio_m2_lista / coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto)
        ELSE NULL
    END AS indice_precio_vs_benchmark_interno,
    CASE
        WHEN coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto) IS NULL THEN 'SIN_BENCHMARK'
        WHEN b.precio_m2_lista < 0.95 * coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto) THEN 'BAJO_CORREDOR'
        WHEN b.precio_m2_lista > 1.05 * coalesce(s.mediana_precio_m2_segmento, p.mediana_precio_m2_proyecto) THEN 'SOBRE_CORREDOR'
        ELSE 'EN_CORREDOR'
    END AS posicion_precio_interno
FROM base b
LEFT JOIN segment_stats s
  ON s.codigo_proyecto IS NOT DISTINCT FROM b.codigo_proyecto
 AND s.segmento = coalesce(nullif(b.nombre_tipologia, ''), nullif(b.tipologia_ubicacion, ''), 'SIN_TIPOLOGIA')
LEFT JOIN project_stats p
  ON p.codigo_proyecto IS NOT DISTINCT FROM b.codigo_proyecto;

CREATE OR REPLACE VIEW pricing_analytics.v_pricing_project_scorecard AS
WITH units AS (
    SELECT
        codigo_proyecto,
        max(nombre_proyecto) AS nombre_proyecto,
        count(*) FILTER (WHERE tipo_unidad = 'Departamento') AS departamentos_total,
        count(*) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'DISPONIBLE') AS departamentos_disponibles,
        count(*) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'NO_DISPONIBLE') AS departamentos_no_disponibles,
        count(*) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'SEPARADO') AS departamentos_separados,
        count(*) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'VENDIDO') AS departamentos_vendidos,
        sum(precio_lista) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'DISPONIBLE') AS valor_lista_disponible,
        avg(precio_lista) FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'DISPONIBLE') AS precio_lista_promedio_disponible,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY precio_m2_lista)
            FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'DISPONIBLE' AND precio_m2_lista IS NOT NULL)
            AS precio_m2_mediana_disponible,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY precio_m2_venta)
            FILTER (WHERE tipo_unidad = 'Departamento' AND estado_bucket = 'VENDIDO' AND precio_m2_venta IS NOT NULL)
            AS precio_m2_mediana_vendido
    FROM pricing_analytics.v_pricing_unit_current
    GROUP BY codigo_proyecto
), latest_abs AS (
    SELECT DISTINCT ON (codigo_proyecto)
        codigo_proyecto,
        fecha AS fecha_absorcion,
        stock_inicio,
        stock_fin,
        separaciones_netas_30d,
        ventas_30d,
        absorcion_neta_30d,
        conversion_sep_venta_30d,
        tasa_caida_30d,
        velocidad_venta_diaria_30d,
        meses_stock_ventas_30d
    FROM analytics.fact_absorcion_proyecto_diario
    ORDER BY codigo_proyecto, fecha DESC
)
SELECT
    u.*,
    a.fecha_absorcion,
    a.stock_inicio,
    a.stock_fin,
    a.separaciones_netas_30d,
    a.ventas_30d,
    a.absorcion_neta_30d,
    a.conversion_sep_venta_30d,
    a.tasa_caida_30d,
    a.velocidad_venta_diaria_30d,
    a.meses_stock_ventas_30d,
    CASE
        WHEN u.precio_m2_mediana_vendido > 0
            THEN u.precio_m2_mediana_disponible / u.precio_m2_mediana_vendido - 1
        ELSE NULL
    END AS gap_precio_m2_disponible_vs_vendido
FROM units u
LEFT JOIN latest_abs a
  ON a.codigo_proyecto IS NOT DISTINCT FROM u.codigo_proyecto;

CREATE OR REPLACE VIEW pricing_analytics.v_price_change_events AS
WITH ordered AS (
    SELECT
        snapshot_date,
        unidad_fuente_key,
        esquema_fuente,
        codigo_unidad,
        codigo_proyecto,
        nombre_proyecto,
        tipo_unidad,
        nombre_tipologia,
        tipologia_ubicacion,
        estado_comercial,
        precio_lista,
        precio_m2_lista_calc,
        lag(precio_lista) OVER (
            PARTITION BY unidad_fuente_key
            ORDER BY snapshot_date
        ) AS precio_lista_anterior,
        lag(precio_m2_lista_calc) OVER (
            PARTITION BY unidad_fuente_key
            ORDER BY snapshot_date
        ) AS precio_m2_anterior
    FROM pricing_analytics.fact_precio_unidad_diario
)
SELECT
    *,
    precio_lista - precio_lista_anterior AS delta_precio_lista,
    CASE
        WHEN precio_lista_anterior > 0
            THEN precio_lista / precio_lista_anterior - 1
        ELSE NULL
    END AS delta_precio_pct,
    CASE
        WHEN precio_m2_anterior > 0
            THEN precio_m2_lista_calc / precio_m2_anterior - 1
        ELSE NULL
    END AS delta_precio_m2_pct
FROM ordered
WHERE precio_lista_anterior IS NOT NULL
  AND precio_lista IS DISTINCT FROM precio_lista_anterior;

COMMENT ON TABLE pricing_analytics.fact_precio_unidad_diario IS
'Histórico diario de precios de unidad capturado desde core.v_unidades_fuentes. Preserva provenance y habilita análisis temporal futuro.';

COMMENT ON VIEW pricing_analytics.v_pricing_unit_positioning IS
'Posicionamiento de precio m2 contra benchmark interno por proyecto/tipología. No representa benchmark de mercado externo.';

COMMENT ON VIEW pricing_analytics.v_pricing_project_scorecard IS
'Scorecard ejecutivo que une stock/precio actual con la última absorción canónica disponible en Medallio.';

COMMENT ON VIEW pricing_analytics.v_price_change_events IS
'Eventos observados de cambio de precio. Son evidencia de variación, no estimaciones causales de elasticidad.';
