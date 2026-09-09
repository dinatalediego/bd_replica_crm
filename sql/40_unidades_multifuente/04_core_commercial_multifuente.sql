-- Capa comercial gobernada multi-fuente para consumo BI.
-- No reemplaza core.dim_unidad (certificada desde CRM); la complementa con inventario externo.
-- Preserva provenance y evita tratar raw_mercado como si tuviera el mismo ledger transaccional.

CREATE OR REPLACE VIEW core.v_unidad_comercial_multifuente AS
SELECT
    u.esquema_fuente,
    u.esquema_fuente AS fuente_esquema, -- alias temporal de compatibilidad con modelos Power BI existentes
    u.unidad_fuente_key,
    u.unidad_id_fuente,
    u.codigo AS codigo_unidad,
    u.codigo_proyecto,
    COALESCE(p.nombre_proyecto, u.nombre_proyecto) AS nombre_proyecto,
    u.nombre AS nombre_unidad,
    u.codigo_subdivision,
    u.nombre_subdivision,
    u.tipo_unidad,
    u.piso,
    u.estado_construccion,
    u.nombre_tipologia,
    u.tipologia_ubicacion,
    u.total_habitaciones,
    u.total_banos,
    u.area_libre,
    u.area_techada,
    u.area_total,
    u.estado_comercial,
    u.estado_personalizado,
    u.codigo_proforma AS codigo_proforma_actual,
    u.precio_lista AS precio_lista_actual,
    u.precio_base_proforma AS precio_base_proforma_actual,
    u.descuento_venta AS descuento_venta_actual,
    u.precio_venta AS precio_venta_actual,
    u.precio_m2 AS precio_m2_actual,
    u.fecha_reserva AS fecha_reserva_actual,
    u.fecha_separacion AS fecha_separacion_actual,
    u.fecha_venta AS fecha_venta_actual,
    u.fecha_entrega,
    u.modalidad_contrato,
    u.codigo_externo,
    u.fecha_precio_actualizado,
    u.moneda_precio_lista,
    u.moneda_venta,
    u.fecha_actualizacion AS fecha_actualizacion_origen,
    u.fecha_estimada_entrega,
    u.source_loaded_at,
    u.source_run_id,
    (p.proyecto_id IS NOT NULL) AS proyecto_en_core,
    (u.esquema_fuente = 'raw_cygnus') AS tiene_ledger_crm,
    CASE
        WHEN u.esquema_fuente = 'raw_cygnus' THEN 'CRM_OBSERVADO'
        WHEN u.esquema_fuente = 'raw_mercado' THEN 'MERCADO_EXTERNO'
        ELSE 'OTRA_FUENTE'
    END::text AS nivel_evidencia_comercial
FROM core.v_unidades_fuentes u
LEFT JOIN core.dim_proyecto p
  ON p.codigo_proyecto = u.codigo_proyecto;

COMMENT ON VIEW core.v_unidad_comercial_multifuente IS
'Unidad comercial actual Cygnus + mercado para Power BI. Conserva esquema_fuente, tipologia_ubicacion y nivel de evidencia; raw_mercado no se interpreta como ledger CRM.';

CREATE OR REPLACE VIEW analytics_compare.v_powerbi_unidad_actual AS
SELECT
    esquema_fuente,
    fuente_esquema,
    unidad_fuente_key,
    unidad_id_fuente,
    codigo_unidad,
    codigo_proyecto,
    nombre_proyecto,
    nombre_unidad,
    tipo_unidad,
    piso,
    nombre_tipologia,
    tipologia_ubicacion,
    total_habitaciones,
    total_banos,
    area_libre,
    area_techada,
    area_total,
    estado_comercial,
    estado_personalizado,
    codigo_proforma_actual,
    precio_lista_actual,
    precio_venta_actual,
    precio_m2_actual,
    fecha_reserva_actual,
    fecha_separacion_actual,
    fecha_venta_actual,
    moneda_precio_lista,
    moneda_venta,
    fecha_actualizacion_origen,
    source_loaded_at,
    source_run_id,
    proyecto_en_core,
    tiene_ledger_crm,
    nivel_evidencia_comercial,
    CASE
        WHEN lower(coalesce(estado_comercial, '')) IN ('disponible', 'bloqueado') THEN 1
        ELSE 0
    END::integer AS flag_stock_actual
FROM core.v_unidad_comercial_multifuente;

COMMENT ON VIEW analytics_compare.v_powerbi_unidad_actual IS
'Vista de unidad lista para Power BI con 1 fila por unidad/fuente y provenance explícita.';
