-- Capa canónica de unidades multi-fuente.
-- Mantiene provenance explícita y no mezcla historia de procesos.
-- raw_cygnus: inventario/CRM propio.
-- raw_mercado: inventario externo cargado por CSV.
--
-- Compatibilidad:
-- * raw_cygnus usa el contrato canónico actual.
-- * raw_mercado se adapta vía to_jsonb porque instalaciones locales antiguas
--   pueden conservar nombres como codigo_unidad / tipologia / estado / area_venta.
--   De este modo una columna ausente no rompe la creación de la vista.

CREATE SCHEMA IF NOT EXISTS core;

CREATE OR REPLACE VIEW core.v_unidades_fuentes AS
SELECT
    'raw_cygnus'::text AS esquema_fuente,
    ('raw_cygnus:' || u.codigo::text) AS unidad_fuente_key,
    u.id::bigint AS unidad_id_fuente,
    u.codigo::text AS codigo,
    u.nombre::text AS nombre,
    u.codigo_proyecto::text AS codigo_proyecto,
    u.nombre_proyecto::text AS nombre_proyecto,
    u.codigo_subdivision::text AS codigo_subdivision,
    u.nombre_subdivision::text AS nombre_subdivision,
    u.tipo_unidad::text AS tipo_unidad,
    u.piso::text AS piso,
    u.estado_construccion::text AS estado_construccion,
    u.nombre_tipologia::text AS nombre_tipologia,
    u.total_habitaciones::numeric AS total_habitaciones,
    u.total_banos::integer AS total_banos,
    u.area_libre::numeric AS area_libre,
    u.area_techada::numeric AS area_techada,
    u.area_total::numeric AS area_total,
    u.estado_comercial::text AS estado_comercial,
    u.estado_personalizado::text AS estado_personalizado,
    u.codigo_proforma::text AS codigo_proforma,
    u.precio_lista::numeric AS precio_lista,
    u.precio_base_proforma::numeric AS precio_base_proforma,
    u.descuento_venta::numeric AS descuento_venta,
    u.precio_venta::numeric AS precio_venta,
    u.precio_m2::numeric AS precio_m2,
    u.fecha_reserva::date AS fecha_reserva,
    u.fecha_separacion::date AS fecha_separacion,
    u.fecha_venta::date AS fecha_venta,
    u.fecha_entrega::date AS fecha_entrega,
    u.modalidad_contrato::text AS modalidad_contrato,
    u.codigo_externo::text AS codigo_externo,
    u.fecha_precio_actualizado::date AS fecha_precio_actualizado,
    u.moneda_precio_lista::text AS moneda_precio_lista,
    u.moneda_venta::text AS moneda_venta,
    u.fecha_actualizacion::date AS fecha_actualizacion,
    u.fecha_estimada_entrega::date AS fecha_estimada_entrega,
    u._etl_loaded_at::timestamptz AS source_loaded_at,
    u._etl_source_run_id::text AS source_run_id,
    (to_jsonb(u)->>'tipologia_ubicacion')::text AS tipologia_ubicacion
FROM raw_cygnus.unidades u

UNION ALL

SELECT
    'raw_mercado'::text AS esquema_fuente,
    'raw_mercado:' || coalesce(nullif(m.j->>'codigo', ''), nullif(m.j->>'codigo_unidad', ''), nullif(m.j->>'id', ''), 'sin_codigo') AS unidad_fuente_key,
    CASE WHEN coalesce(m.j->>'id','') ~ '^[0-9]+$' THEN (m.j->>'id')::bigint ELSE NULL::bigint END AS unidad_id_fuente,
    coalesce(nullif(m.j->>'codigo', ''), nullif(m.j->>'codigo_unidad', ''))::text AS codigo,
    coalesce(nullif(m.j->>'nombre', ''), nullif(m.j->>'unidad', ''))::text AS nombre,
    coalesce(nullif(m.j->>'codigo_proyecto', ''), nullif(m.j->>'proyecto_codigo', ''), nullif(m.j->>'cod_proyecto', ''))::text AS codigo_proyecto,
    coalesce(nullif(m.j->>'nombre_proyecto', ''), nullif(m.j->>'proyecto', ''))::text AS nombre_proyecto,
    nullif(m.j->>'codigo_subdivision', '')::text AS codigo_subdivision,
    nullif(m.j->>'nombre_subdivision', '')::text AS nombre_subdivision,
    coalesce(nullif(m.j->>'tipo_unidad', ''), nullif(m.j->>'tipo', ''))::text AS tipo_unidad,
    nullif(m.j->>'piso', '')::text AS piso,
    nullif(m.j->>'estado_construccion', '')::text AS estado_construccion,
    coalesce(nullif(m.j->>'nombre_tipologia', ''), nullif(m.j->>'tipologia', ''))::text AS nombre_tipologia,
    CASE WHEN coalesce(m.j->>'total_habitaciones', m.j->>'dormitorios', '') ~ '^-?[0-9]+([.][0-9]+)?$'
         THEN coalesce(m.j->>'total_habitaciones', m.j->>'dormitorios')::numeric ELSE NULL::numeric END AS total_habitaciones,
    CASE WHEN coalesce(m.j->>'total_banos','') ~ '^[0-9]+$' THEN (m.j->>'total_banos')::integer ELSE NULL::integer END AS total_banos,
    CASE WHEN coalesce(m.j->>'area_libre','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'area_libre')::numeric ELSE NULL::numeric END AS area_libre,
    CASE WHEN coalesce(m.j->>'area_techada','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'area_techada')::numeric ELSE NULL::numeric END AS area_techada,
    CASE WHEN coalesce(m.j->>'area_total', m.j->>'area_venta', '') ~ '^-?[0-9]+([.][0-9]+)?$'
         THEN coalesce(m.j->>'area_total', m.j->>'area_venta')::numeric ELSE NULL::numeric END AS area_total,
    coalesce(nullif(m.j->>'estado_comercial', ''), nullif(m.j->>'estado', ''))::text AS estado_comercial,
    nullif(m.j->>'estado_personalizado', '')::text AS estado_personalizado,
    nullif(m.j->>'codigo_proforma', '')::text AS codigo_proforma,
    CASE WHEN coalesce(m.j->>'precio_lista','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'precio_lista')::numeric ELSE NULL::numeric END AS precio_lista,
    CASE WHEN coalesce(m.j->>'precio_base_proforma','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'precio_base_proforma')::numeric ELSE NULL::numeric END AS precio_base_proforma,
    CASE WHEN coalesce(m.j->>'descuento_venta','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'descuento_venta')::numeric ELSE NULL::numeric END AS descuento_venta,
    CASE WHEN coalesce(m.j->>'precio_venta','') ~ '^-?[0-9]+([.][0-9]+)?$' THEN (m.j->>'precio_venta')::numeric ELSE NULL::numeric END AS precio_venta,
    CASE WHEN coalesce(m.j->>'precio_m2', m.j->>'pxm2', '') ~ '^-?[0-9]+([.][0-9]+)?$'
         THEN coalesce(m.j->>'precio_m2', m.j->>'pxm2')::numeric ELSE NULL::numeric END AS precio_m2,
    CASE WHEN coalesce(m.j->>'fecha_reserva','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_reserva',10)::date ELSE NULL::date END AS fecha_reserva,
    CASE WHEN coalesce(m.j->>'fecha_separacion','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_separacion',10)::date ELSE NULL::date END AS fecha_separacion,
    CASE WHEN coalesce(m.j->>'fecha_venta','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_venta',10)::date ELSE NULL::date END AS fecha_venta,
    CASE WHEN coalesce(m.j->>'fecha_entrega','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_entrega',10)::date ELSE NULL::date END AS fecha_entrega,
    nullif(m.j->>'modalidad_contrato', '')::text AS modalidad_contrato,
    nullif(m.j->>'codigo_externo', '')::text AS codigo_externo,
    CASE WHEN coalesce(m.j->>'fecha_precio_actualizado','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_precio_actualizado',10)::date ELSE NULL::date END AS fecha_precio_actualizado,
    coalesce(nullif(m.j->>'moneda_precio_lista',''), nullif(m.j->>'moneda',''))::text AS moneda_precio_lista,
    nullif(m.j->>'moneda_venta', '')::text AS moneda_venta,
    CASE WHEN coalesce(m.j->>'fecha_actualizacion','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_actualizacion',10)::date ELSE NULL::date END AS fecha_actualizacion,
    CASE WHEN coalesce(m.j->>'fecha_estimada_entrega','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN left(m.j->>'fecha_estimada_entrega',10)::date ELSE NULL::date END AS fecha_estimada_entrega,
    CASE WHEN coalesce(m.j->>'_etl_loaded_at','') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN (m.j->>'_etl_loaded_at')::timestamptz ELSE NULL::timestamptz END AS source_loaded_at,
    nullif(m.j->>'_etl_source_run_id', '')::text AS source_run_id,
    nullif(m.j->>'tipologia_ubicacion', '')::text AS tipologia_ubicacion
FROM (
    SELECT to_jsonb(u) AS j
    FROM raw_mercado.unidades u
) m;

COMMENT ON VIEW core.v_unidades_fuentes IS
'Vista canónica de unidades de raw_cygnus y raw_mercado. raw_mercado usa adaptador JSON tolerante a contratos históricos.';
