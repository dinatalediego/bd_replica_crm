-- Capa comparativa lista para BI.
-- Unifica estado actual y una métrica de absorción comparable sin perder provenance.

CREATE SCHEMA IF NOT EXISTS analytics_compare;

CREATE OR REPLACE VIEW analytics_compare.v_inventario_actual AS
SELECT
    esquema_fuente,
    unidad_fuente_key,
    codigo,
    codigo_proyecto,
    nombre_proyecto,
    nombre_tipologia,
    total_habitaciones,
    tipo_unidad,
    piso,
    area_total,
    area_techada,
    area_libre,
    estado_comercial,
    precio_lista,
    precio_venta,
    precio_m2,
    fecha_separacion,
    fecha_venta,
    source_loaded_at,
    source_run_id,
    CASE
        WHEN lower(coalesce(estado_comercial, '')) IN ('disponible','bloqueado') THEN 1
        ELSE 0
    END::integer AS flag_stock_actual,
    CASE
        WHEN fecha_separacion IS NOT NULL THEN 1
        ELSE 0
    END::integer AS flag_separado_historico
FROM core.v_unidades_fuentes;

COMMENT ON VIEW analytics_compare.v_inventario_actual IS
'Inventario consolidado Cygnus + mercado para Power BI, con esquema_fuente como dimensión obligatoria.';

CREATE OR REPLACE VIEW analytics_compare.v_kpi_inventario_proyecto AS
SELECT
    esquema_fuente,
    codigo_proyecto,
    max(nombre_proyecto) AS nombre_proyecto,
    count(*)::bigint AS unidades_total,
    count(*) FILTER (WHERE flag_stock_actual = 1)::bigint AS unidades_stock_actual,
    count(*) FILTER (WHERE flag_separado_historico = 1)::bigint AS unidades_con_separacion,
    sum(precio_lista) FILTER (WHERE flag_stock_actual = 1)::numeric AS valor_lista_stock_actual,
    avg(precio_m2) FILTER (WHERE flag_stock_actual = 1 AND precio_m2 > 0)::numeric AS precio_m2_promedio_stock,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY precio_m2)
        FILTER (WHERE flag_stock_actual = 1 AND precio_m2 > 0)::numeric AS precio_m2_mediana_stock,
    avg(area_total) FILTER (WHERE area_total > 0)::numeric AS area_promedio,
    min(fecha_separacion) AS primera_fecha_separacion,
    max(fecha_separacion) AS ultima_fecha_separacion
FROM analytics_compare.v_inventario_actual
GROUP BY esquema_fuente, codigo_proyecto;

COMMENT ON VIEW analytics_compare.v_kpi_inventario_proyecto IS
'KPIs actuales por proyecto y fuente: stock, valor, precio/m2 y fechas de separación.';

CREATE OR REPLACE VIEW analytics_compare.v_composicion_tipologia AS
SELECT
    esquema_fuente,
    codigo_proyecto,
    max(nombre_proyecto) AS nombre_proyecto,
    nombre_tipologia,
    total_habitaciones,
    count(*)::bigint AS unidades,
    count(*) FILTER (WHERE flag_stock_actual = 1)::bigint AS stock_actual,
    avg(area_total) FILTER (WHERE area_total > 0)::numeric AS area_promedio,
    avg(precio_m2) FILTER (WHERE precio_m2 > 0)::numeric AS precio_m2_promedio,
    avg(precio_lista) FILTER (WHERE precio_lista > 0)::numeric AS precio_lista_promedio
FROM analytics_compare.v_inventario_actual
GROUP BY esquema_fuente, codigo_proyecto, nombre_tipologia, total_habitaciones;

COMMENT ON VIEW analytics_compare.v_composicion_tipologia IS
'Composición de inventario por fuente, proyecto, tipología y dormitorios para análisis comparativo.';

CREATE OR REPLACE VIEW analytics_compare.v_absorcion_proyecto_diario AS
SELECT
    'raw_cygnus'::text AS esquema_fuente,
    a.fecha,
    a.codigo_proyecto,
    a.stock_inicio::bigint,
    a.stock_fin::bigint,
    a.stock_promedio::numeric,
    a.separaciones_brutas::bigint,
    a.caidas::bigint,
    a.separaciones_netas::bigint,
    a.ventas::bigint,
    a.stock_inicio_ventana_7d::bigint,
    a.absorcion_bruta_7d::numeric,
    a.absorcion_neta_7d::numeric,
    a.stock_inicio_ventana_30d::bigint,
    a.absorcion_bruta_30d::numeric,
    a.absorcion_neta_30d::numeric,
    a.stock_inicio_ventana_90d::bigint,
    a.absorcion_bruta_90d::numeric,
    a.absorcion_neta_90d::numeric,
    'OBSERVADO_RECONCILIADO'::text AS nivel_evidencia,
    'LEDGER_CYGNUS'::text AS metodo_absorcion
FROM analytics.fact_absorcion_proyecto_diario a

UNION ALL

SELECT
    m.esquema_fuente,
    m.fecha,
    m.codigo_proyecto,
    m.stock_inicio,
    m.stock_fin,
    m.stock_promedio,
    m.separaciones_brutas,
    m.caidas,
    m.separaciones_netas,
    m.ventas,
    m.stock_inicio_ventana_7d,
    m.absorcion_bruta_7d,
    m.absorcion_neta_7d,
    m.stock_inicio_ventana_30d,
    m.absorcion_bruta_30d,
    m.absorcion_neta_30d,
    m.stock_inicio_ventana_90d,
    m.absorcion_bruta_90d,
    m.absorcion_neta_90d,
    m.nivel_evidencia,
    m.metodo_absorcion
FROM analytics_market.v_absorcion_proyecto_diario_inferida m;

COMMENT ON VIEW analytics_compare.v_absorcion_proyecto_diario IS
'Absorción diaria comparable: Cygnus observada/reconciliada y mercado inferido. nivel_evidencia evita tratarlas como equivalentes metodológicamente.';

CREATE OR REPLACE VIEW analytics_compare.v_powerbi_proyecto_actual AS
WITH latest_absorption AS (
    SELECT DISTINCT ON (esquema_fuente, codigo_proyecto)
        esquema_fuente,
        codigo_proyecto,
        fecha AS fecha_absorcion,
        stock_fin AS stock_fin_reconstruido,
        absorcion_bruta_30d,
        absorcion_neta_30d,
        nivel_evidencia,
        metodo_absorcion
    FROM analytics_compare.v_absorcion_proyecto_diario
    ORDER BY esquema_fuente, codigo_proyecto, fecha DESC
)
SELECT
    k.esquema_fuente,
    k.codigo_proyecto,
    k.nombre_proyecto,
    k.unidades_total,
    k.unidades_stock_actual,
    k.unidades_con_separacion,
    k.valor_lista_stock_actual,
    k.precio_m2_promedio_stock,
    k.precio_m2_mediana_stock,
    k.area_promedio,
    k.primera_fecha_separacion,
    k.ultima_fecha_separacion,
    a.fecha_absorcion,
    a.stock_fin_reconstruido,
    a.absorcion_bruta_30d,
    a.absorcion_neta_30d,
    a.nivel_evidencia,
    a.metodo_absorcion
FROM analytics_compare.v_kpi_inventario_proyecto k
LEFT JOIN latest_absorption a
  ON a.esquema_fuente = k.esquema_fuente
 AND a.codigo_proyecto = k.codigo_proyecto;

COMMENT ON VIEW analytics_compare.v_powerbi_proyecto_actual IS
'Vista compacta de proyecto/fuente para Power BI: inventario actual, precio/m2 y última absorción 30d disponible.';
