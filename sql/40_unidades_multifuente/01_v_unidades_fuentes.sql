-- Capa canónica de unidades multi-fuente con compatibilidad para contratos RAW históricos.
-- La extracción JSONB permite leer codigo o codigo_unidad sin alterar el origen.

CREATE SCHEMA IF NOT EXISTS core;

CREATE OR REPLACE VIEW core.v_unidades_fuentes AS
WITH base AS (
    SELECT 'raw_cygnus'::text AS esquema_fuente, to_jsonb(u) AS j FROM raw_cygnus.unidades u
    UNION ALL
    SELECT 'raw_mercado'::text AS esquema_fuente, to_jsonb(u) AS j FROM raw_mercado.unidades u
), normalized AS (
    SELECT
        esquema_fuente,
        COALESCE(NULLIF(btrim(j->>'codigo'), ''), NULLIF(btrim(j->>'codigo_unidad'), '')) AS codigo,
        j
    FROM base
), typed AS (
    SELECT
        esquema_fuente,
        codigo,
        COALESCE(j->>'nombre', j->>'nombre_unidad') AS nombre,
        NULLIF(btrim(j->>'codigo_proyecto'), '') AS codigo_proyecto,
        j->>'nombre_proyecto' AS nombre_proyecto,
        j->>'codigo_subdivision' AS codigo_subdivision,
        j->>'nombre_subdivision' AS nombre_subdivision,
        j->>'tipo_unidad' AS tipo_unidad,
        j->>'piso' AS piso,
        j->>'estado_construccion' AS estado_construccion,
        COALESCE(j->>'nombre_tipologia', j->>'tipologia') AS nombre_tipologia,
        COALESCE(NULLIF(btrim(j->>'tipologia_ubicacion'), ''), right(codigo, 2)) AS tipologia_ubicacion,
        COALESCE(j->>'total_habitaciones', j->>'dormitorios') AS total_habitaciones_raw,
        j->>'total_banos' AS total_banos_raw,
        j->>'area_libre' AS area_libre_raw,
        j->>'area_techada' AS area_techada_raw,
        COALESCE(j->>'area_total', j->>'area_venta') AS area_total_raw,
        COALESCE(j->>'estado_comercial', j->>'estado') AS estado_comercial,
        j->>'estado_personalizado' AS estado_personalizado,
        j->>'codigo_proforma' AS codigo_proforma,
        j->>'precio_lista' AS precio_lista_raw,
        j->>'precio_base_proforma' AS precio_base_proforma_raw,
        j->>'descuento_venta' AS descuento_venta_raw,
        j->>'precio_venta' AS precio_venta_raw,
        COALESCE(j->>'precio_m2', j->>'pxm2') AS precio_m2_raw,
        j->>'fecha_reserva' AS fecha_reserva_raw,
        j->>'fecha_separacion' AS fecha_separacion_raw,
        j->>'fecha_venta' AS fecha_venta_raw,
        j->>'fecha_entrega' AS fecha_entrega_raw,
        j->>'modalidad_contrato' AS modalidad_contrato,
        j->>'codigo_externo' AS codigo_externo,
        j->>'fecha_precio_actualizado' AS fecha_precio_actualizado_raw,
        j->>'moneda_precio_lista' AS moneda_precio_lista,
        j->>'moneda_venta' AS moneda_venta,
        j->>'fecha_actualizacion' AS fecha_actualizacion_raw,
        j->>'fecha_estimada_entrega' AS fecha_estimada_entrega_raw,
        COALESCE(j->>'_etl_loaded_at', j->>'_loaded_at') AS source_loaded_at_raw,
        j->>'_etl_source_run_id' AS source_run_id_raw,
        COALESCE(j->>'id', j->>'source_id') AS id_raw
    FROM normalized
    WHERE codigo IS NOT NULL
)
SELECT
    esquema_fuente,
    esquema_fuente || ':' || codigo AS unidad_fuente_key,
    CASE WHEN id_raw ~ '^[0-9]+$' THEN id_raw::bigint END AS unidad_id_fuente,
    codigo, nombre, codigo_proyecto, nombre_proyecto, codigo_subdivision, nombre_subdivision,
    tipo_unidad, piso, estado_construccion, nombre_tipologia,
    CASE WHEN total_habitaciones_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(total_habitaciones_raw, ',', '.')::numeric END AS total_habitaciones,
    CASE WHEN total_banos_raw ~ '^[+-]?[0-9]+$' THEN total_banos_raw::integer END AS total_banos,
    CASE WHEN area_libre_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(area_libre_raw, ',', '.')::numeric END AS area_libre,
    CASE WHEN area_techada_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(area_techada_raw, ',', '.')::numeric END AS area_techada,
    CASE WHEN area_total_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(area_total_raw, ',', '.')::numeric END AS area_total,
    estado_comercial, estado_personalizado, codigo_proforma,
    CASE WHEN precio_lista_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(precio_lista_raw, ',', '.')::numeric END AS precio_lista,
    CASE WHEN precio_base_proforma_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(precio_base_proforma_raw, ',', '.')::numeric END AS precio_base_proforma,
    CASE WHEN descuento_venta_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(descuento_venta_raw, ',', '.')::numeric END AS descuento_venta,
    CASE WHEN precio_venta_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(precio_venta_raw, ',', '.')::numeric END AS precio_venta,
    CASE WHEN precio_m2_raw ~ '^[+-]?[0-9]+([.,][0-9]+)?$' THEN replace(precio_m2_raw, ',', '.')::numeric END AS precio_m2,
    CASE WHEN fecha_reserva_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_reserva_raw, 10)::date END AS fecha_reserva,
    CASE WHEN fecha_separacion_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_separacion_raw, 10)::date END AS fecha_separacion,
    CASE WHEN fecha_venta_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_venta_raw, 10)::date END AS fecha_venta,
    CASE WHEN fecha_entrega_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_entrega_raw, 10)::date END AS fecha_entrega,
    modalidad_contrato, codigo_externo,
    CASE WHEN fecha_precio_actualizado_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_precio_actualizado_raw, 10)::date END AS fecha_precio_actualizado,
    moneda_precio_lista, moneda_venta,
    CASE WHEN fecha_actualizacion_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_actualizacion_raw, 10)::date END AS fecha_actualizacion,
    CASE WHEN fecha_estimada_entrega_raw ~ '^\d{4}-\d{2}-\d{2}' THEN left(fecha_estimada_entrega_raw, 10)::date END AS fecha_estimada_entrega,
    CASE WHEN source_loaded_at_raw ~ '^\d{4}-\d{2}-\d{2}' THEN source_loaded_at_raw::timestamptz END AS source_loaded_at,
    source_run_id_raw::text AS source_run_id,
    tipologia_ubicacion
FROM typed;

COMMENT ON VIEW core.v_unidades_fuentes IS
'Vista canónica de unidades Cygnus y mercado; acepta contratos históricos codigo_unidad/codigo sin mutar RAW.';
