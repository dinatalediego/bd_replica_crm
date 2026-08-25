from __future__ import annotations

from psycopg import Connection


DDL = """
CREATE SCHEMA IF NOT EXISTS raw_mercado;

CREATE TABLE IF NOT EXISTS raw_mercado.cargas (
    carga_id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL UNIQUE,
    source_id text NOT NULL,
    empresa_fuente text NOT NULL,
    codigo_proyecto text NOT NULL,
    nombre_proyecto text NOT NULL,
    fecha_snapshot date NOT NULL,
    archivo_origen text NOT NULL,
    hoja_origen text,
    hash_archivo text NOT NULL,
    estado text NOT NULL CHECK (estado IN ('STARTED', 'SUCCESS', 'FAILED')),
    filas_leidas integer NOT NULL DEFAULT 0,
    filas_insertadas_historial integer NOT NULL DEFAULT 0,
    filas_actualizadas_actual integer NOT NULL DEFAULT 0,
    advertencias jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    iniciado_en timestamptz NOT NULL DEFAULT now(),
    finalizado_en timestamptz,
    UNIQUE (source_id, hash_archivo)
);

CREATE TABLE IF NOT EXISTS raw_mercado.unidades_historial (
    observacion_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    carga_id uuid NOT NULL REFERENCES raw_mercado.cargas(carga_id),
    snapshot_id uuid NOT NULL,
    source_id text NOT NULL,
    empresa_fuente text NOT NULL,
    codigo_proyecto text NOT NULL,
    nombre_proyecto text NOT NULL,
    fecha_snapshot date NOT NULL,
    codigo_unidad text NOT NULL,
    torre text,
    tipo_unidad text,
    tipologia text,
    numero_inmueble text,
    piso integer,
    vista text,
    area_techada_m2 numeric(12,2),
    area_libre_m2 numeric(12,2),
    area_venta_m2 numeric(12,2),
    dormitorios integer,
    moneda text,
    precio_lista numeric(16,2),
    precio_venta numeric(16,2),
    precio_m2 numeric(16,4),
    fecha_separacion date,
    fecha_venta date,
    estado_comercial text,
    estado_comercial_original text,
    referido text,
    archivo_origen text NOT NULL,
    hoja_origen text,
    fila_origen integer NOT NULL,
    hash_fila text NOT NULL,
    cargado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, codigo_unidad)
);

CREATE INDEX IF NOT EXISTS ix_unidades_historial_unidad_fecha
    ON raw_mercado.unidades_historial
       (source_id, codigo_unidad, fecha_snapshot DESC);

CREATE INDEX IF NOT EXISTS ix_unidades_historial_proyecto_fecha
    ON raw_mercado.unidades_historial
       (codigo_proyecto, fecha_snapshot DESC);

CREATE TABLE IF NOT EXISTS raw_mercado.unidades (
    source_id text NOT NULL,
    codigo_unidad text NOT NULL,
    carga_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    empresa_fuente text NOT NULL,
    codigo_proyecto text NOT NULL,
    nombre_proyecto text NOT NULL,
    fecha_snapshot date NOT NULL,
    torre text,
    tipo_unidad text,
    tipologia text,
    numero_inmueble text,
    piso integer,
    vista text,
    area_techada_m2 numeric(12,2),
    area_libre_m2 numeric(12,2),
    area_venta_m2 numeric(12,2),
    dormitorios integer,
    moneda text,
    precio_lista numeric(16,2),
    precio_venta numeric(16,2),
    precio_m2 numeric(16,4),
    fecha_separacion date,
    fecha_venta date,
    estado_comercial text,
    estado_comercial_original text,
    referido text,
    archivo_origen text NOT NULL,
    hoja_origen text,
    fila_origen integer NOT NULL,
    hash_fila text NOT NULL,
    cargado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, codigo_unidad)
);

CREATE INDEX IF NOT EXISTS ix_unidades_actual_proyecto_estado
    ON raw_mercado.unidades (codigo_proyecto, estado_comercial);

CREATE OR REPLACE VIEW raw_mercado.v_unidades_actual AS
SELECT * FROM raw_mercado.unidades;
"""


def ensure_schema(conn: Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(DDL)
    conn.commit()

