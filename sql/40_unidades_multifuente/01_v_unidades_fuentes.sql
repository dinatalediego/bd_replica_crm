-- Capa canónica de unidades multi-fuente.
-- Mantiene provenance explícita y no mezcla historia de procesos.
-- raw_cygnus: inventario/CRM propio.
-- raw_mercado: inventario externo cargado por CSV.

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
    u._etl_loaded_at AS source_loaded_at,
    u._etl_source_run_id AS source_run_id
FROM raw_cygnus.unidades u

UNION ALL

SELECT
    'raw_mercado'::text AS esquema_fuente,
    ('raw_mercado:' || u.codigo::text) AS unidad_fuente_key,
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
    u._etl_loaded_at AS source_loaded_at,
    u._etl_source_run_id AS source_run_id
FROM raw_mercado.unidades u;

COMMENT ON VIEW core.v_unidades_fuentes IS
'Vista canónica de unidades de raw_cygnus y raw_mercado con provenance explícita en esquema_fuente.';
