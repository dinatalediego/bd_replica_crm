-- CORE Commercial Model v1
-- Entidades comerciales certificadas a partir de raw_cygnus.
--
-- Semántica v1:
--   dim_proyecto = estado actual de cada proyecto.
--   dim_unidad   = estado actual de cada unidad.
--
-- La historia de precios, stock, separaciones y ventas no se modela aquí.
-- Esa historia deberá vivir posteriormente en hechos/snapshots temporales.

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.dim_proyecto (
    proyecto_id                  integer PRIMARY KEY,
    codigo_proyecto              text NOT NULL UNIQUE,
    nombre_proyecto              text,
    direccion                    text,
    fecha_estimacion             date,
    fecha_real                   date,
    fecha_inicio_venta           date,
    latitud                      double precision,
    longitud                     double precision,
    pais                         text,
    departamento                 text,
    provincia                    text,
    distrito                     text,
    usuario_creador              text,
    username                     text,
    tipo_proyecto                text,
    estado_construccion          text,
    total_unidades_reportado     bigint,
    unidades_vendidas_reportado  bigint,
    moneda                       text,
    codigo_externo               text,
    tasa_interes_mensual         numeric,
    banco_promotor               text,
    fecha_actualizacion_origen   date,
    razon_social                 text,
    direccion_razon_social       text,
    ruc_razon_social             text,
    source_loaded_at             timestamptz,
    source_run_id                uuid,
    core_loaded_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_dim_proyecto_distrito
    ON core.dim_proyecto (distrito);
CREATE INDEX IF NOT EXISTS ix_dim_proyecto_estado
    ON core.dim_proyecto (estado_construccion);

CREATE TABLE IF NOT EXISTS core.dim_unidad (
    unidad_id                         integer PRIMARY KEY,
    codigo_unidad                     text NOT NULL UNIQUE,
    codigo_proyecto                   text NOT NULL
        REFERENCES core.dim_proyecto(codigo_proyecto),
    nombre_unidad                     text,
    nombre_proyecto_origen            text,
    codigo_subdivision                text,
    nombre_subdivision                text,
    tipo_unidad                       text,
    piso                              text,
    estado_construccion               text,
    nombre_tipologia                  text,
    tipologia_ubicacion               text,
    total_habitaciones                numeric,
    total_banos                       integer,
    area_libre                        numeric,
    area_techada                      numeric,
    area_total                        numeric,
    estado_comercial                  text,
    estado_personalizado              text,
    codigo_proforma_actual            text,
    precio_lista_actual               numeric,
    precio_base_proforma_actual       numeric,
    descuento_venta_actual            numeric,
    precio_venta_actual               numeric,
    precio_m2_actual                  numeric,
    fecha_reserva_actual              date,
    fecha_separacion_actual           date,
    fecha_venta_actual                date,
    fecha_entrega                     date,
    fecha_inicio_independizacion      date,
    fecha_fin_independizacion         date,
    modalidad_contrato                text,
    codigo_externo                    text,
    fecha_precio_actualizado          date,
    moneda_precio_lista               text,
    moneda_venta                      text,
    vcto_garantia_estructural         date,
    vcto_garantia_acabados            date,
    vcto_garantia_comercial           date,
    padre_id                          integer,
    fecha_actualizacion_origen        date,
    fecha_estimada_entrega            date,
    source_loaded_at                  timestamptz,
    source_run_id                     uuid,
    core_loaded_at                    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_dim_unidad_area_total
        CHECK (area_total IS NULL OR area_total >= 0)
);

-- Upgrade idempotente para instalaciones de CORE creadas antes de
-- tipologia_ubicacion. La derivación vive en CORE, no en Power Query.
ALTER TABLE core.dim_unidad
    ADD COLUMN IF NOT EXISTS tipologia_ubicacion text;

CREATE INDEX IF NOT EXISTS ix_dim_unidad_proyecto
    ON core.dim_unidad (codigo_proyecto);
CREATE INDEX IF NOT EXISTS ix_dim_unidad_estado_comercial
    ON core.dim_unidad (estado_comercial);
CREATE INDEX IF NOT EXISTS ix_dim_unidad_tipo
    ON core.dim_unidad (tipo_unidad);
CREATE INDEX IF NOT EXISTS ix_dim_unidad_tipologia_ubicacion
    ON core.dim_unidad (tipologia_ubicacion);
