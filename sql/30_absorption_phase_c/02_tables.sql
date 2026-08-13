
CREATE TABLE IF NOT EXISTS analytics.dim_fecha (
    fecha date PRIMARY KEY,
    anio integer NOT NULL,
    trimestre integer NOT NULL,
    mes_numero integer NOT NULL,
    mes_nombre text NOT NULL,
    periodo_mes date NOT NULL,
    dia_mes integer NOT NULL,
    dia_semana_numero integer NOT NULL,
    dia_semana_nombre text NOT NULL,
    es_fin_semana boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics.fact_ventas_detalle (
    sale_key text PRIMARY KEY,
    codigo_proforma text NOT NULL,
    codigo_unidad text NOT NULL,
    codigo_proyecto text,

    separacion_source_id bigint,
    venta_source_id bigint,
    datos_extras_fecha_minuta_id bigint,

    fecha_entrada_stock date,
    fecha_separacion_raw date,
    fecha_separacion date,
    fecha_firma_legacy date,
    fecha_de_minuta date,
    fecha_venta_documental date,
    fecha_venta date NOT NULL,
    metodo_fecha_venta text NOT NULL,

    primera_fecha_caida date,

    resultado_documental text,
    resultado_inventario text,
    resultado_canonico text NOT NULL,
    reconciliation_status text NOT NULL,
    confidence_level text NOT NULL,

    documento_cliente text,
    asesor text,
    tipo_unidad_principal text,

    dias_separacion_venta integer,
    refreshed_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(codigo_proforma,codigo_unidad)
);

CREATE TABLE IF NOT EXISTS analytics.agg_ventas_mensual (
    periodo_mes date NOT NULL,
    codigo_proyecto text NOT NULL,

    separaciones_brutas bigint NOT NULL DEFAULT 0,
    caidas bigint NOT NULL DEFAULT 0,
    separaciones_netas bigint NOT NULL DEFAULT 0,
    ventas bigint NOT NULL DEFAULT 0,

    conversion_sep_venta numeric,
    tasa_caida numeric,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(periodo_mes,codigo_proyecto)
);

CREATE TABLE IF NOT EXISTS analytics.dim_periodo_comercial_proyecto (
    codigo_proyecto text PRIMARY KEY,
    nombre_proyecto text,
    fecha_inicio_venta_declarada date,
    fecha_inicio_comercial_observada date,
    fecha_ultima_actividad_comercial_observada date,
    metodo_inicio_observado text,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.fact_stock_ofertado_diario (
    fecha date NOT NULL,
    codigo_proyecto text NOT NULL,

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
    PRIMARY KEY(fecha,codigo_proyecto)
);

CREATE TABLE IF NOT EXISTS analytics.fact_absorcion_proyecto_diario (
    fecha date NOT NULL,
    codigo_proyecto text NOT NULL,

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

    dias_promedio_sep_venta_30d numeric,
    dias_promedio_sep_caida_30d numeric,

    velocidad_venta_diaria_30d numeric,
    meses_stock_ventas_30d numeric,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(fecha,codigo_proyecto)
);
