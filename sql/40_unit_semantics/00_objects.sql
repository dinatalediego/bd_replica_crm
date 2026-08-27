CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.dim_unidad_semantica (
    codigo_unidad text PRIMARY KEY,
    codigo_proyecto text,
    tipo_unidad_origen text,
    tipo_unidad_consolidado text NOT NULL,

    flag_departamento boolean NOT NULL DEFAULT false,
    flag_estacionamiento boolean NOT NULL DEFAULT false,
    flag_deposito boolean NOT NULL DEFAULT false,
    flag_local boolean NOT NULL DEFAULT false,
    flag_otro_tipo boolean NOT NULL DEFAULT false,

    estado_comercial_origen text,
    estado_personalizado_origen text,
    estado_inventario_canonico text,
    estado_comercial_consolidado text NOT NULL,

    flag_disponible boolean NOT NULL DEFAULT false,
    flag_bloqueado boolean NOT NULL DEFAULT false,
    flag_estado_separado boolean NOT NULL DEFAULT false,
    flag_vendido boolean NOT NULL DEFAULT false,
    flag_otro_estado boolean NOT NULL DEFAULT false,
    orden_estado integer NOT NULL,

    refreshed_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_dim_unidad_semantica_tipo_onehot CHECK (
        (flag_departamento::int + flag_estacionamiento::int + flag_deposito::int + flag_local::int + flag_otro_tipo::int) = 1
    ),
    CONSTRAINT ck_dim_unidad_semantica_estado_onehot CHECK (
        (flag_disponible::int + flag_bloqueado::int + flag_estado_separado::int + flag_vendido::int + flag_otro_estado::int) = 1
    )
);

CREATE INDEX IF NOT EXISTS ix_dim_unidad_semantica_proyecto_tipo
    ON analytics.dim_unidad_semantica(codigo_proyecto,tipo_unidad_consolidado);
CREATE INDEX IF NOT EXISTS ix_dim_unidad_semantica_estado
    ON analytics.dim_unidad_semantica(estado_comercial_consolidado,orden_estado);

CREATE TABLE IF NOT EXISTS analytics.fact_stock_ofertado_diario_tipo (
    fecha date NOT NULL,
    codigo_proyecto text NOT NULL,
    tipo_unidad_consolidado text NOT NULL,

    stock_inicio bigint NOT NULL,
    altas bigint NOT NULL,
    separaciones bigint NOT NULL,
    caidas_reingresadas bigint NOT NULL,
    retiros bigint NOT NULL DEFAULT 0,
    ventas bigint NOT NULL,

    delta_stock bigint NOT NULL,
    stock_fin bigint NOT NULL,
    separadas_activas bigint NOT NULL,
    vendidas_acumuladas bigint NOT NULL,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(fecha,codigo_proyecto,tipo_unidad_consolidado)
);

CREATE INDEX IF NOT EXISTS ix_fact_stock_tipo_proyecto_fecha
    ON analytics.fact_stock_ofertado_diario_tipo(codigo_proyecto,tipo_unidad_consolidado,fecha);

CREATE TABLE IF NOT EXISTS analytics.fact_absorcion_proyecto_tipo_diario (
    fecha date NOT NULL,
    codigo_proyecto text NOT NULL,
    tipo_unidad_consolidado text NOT NULL,

    stock_inicio bigint NOT NULL,
    stock_fin bigint NOT NULL,
    stock_promedio numeric,

    separaciones_brutas bigint NOT NULL,
    caidas bigint NOT NULL,
    separaciones_netas bigint NOT NULL,
    ventas bigint NOT NULL,

    separaciones_brutas_7d bigint,
    caidas_7d bigint,
    separaciones_netas_7d bigint,
    ventas_7d bigint,
    stock_inicio_ventana_7d bigint,
    absorcion_bruta_7d numeric,
    absorcion_neta_7d numeric,

    separaciones_brutas_30d bigint,
    caidas_30d bigint,
    separaciones_netas_30d bigint,
    ventas_30d bigint,
    stock_inicio_ventana_30d bigint,
    absorcion_bruta_30d numeric,
    absorcion_neta_30d numeric,

    separaciones_brutas_90d bigint,
    caidas_90d bigint,
    separaciones_netas_90d bigint,
    ventas_90d bigint,
    stock_inicio_ventana_90d bigint,
    absorcion_bruta_90d numeric,
    absorcion_neta_90d numeric,

    conversion_sep_venta_30d numeric,
    tasa_caida_30d numeric,
    velocidad_venta_diaria_30d numeric,
    meses_stock_ventas_30d numeric,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(fecha,codigo_proyecto,tipo_unidad_consolidado)
);

CREATE INDEX IF NOT EXISTS ix_fact_absorcion_tipo_proyecto_fecha
    ON analytics.fact_absorcion_proyecto_tipo_diario(codigo_proyecto,tipo_unidad_consolidado,fecha);
