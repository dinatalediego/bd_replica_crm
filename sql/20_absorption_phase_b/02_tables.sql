CREATE TABLE IF NOT EXISTS analytics.int_unidad_entrada_stock (
    codigo_unidad text PRIMARY KEY,
    codigo_proyecto text,
    fecha_entrada_stock date NOT NULL,
    metodo_fecha_entrada_stock text NOT NULL,
    source_proforma_unidad_id bigint,
    primera_codigo_proforma text,
    source_first_seen_at date,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.int_proforma_minuta (
    codigo_proforma text NOT NULL,
    codigo_unidad text NOT NULL,
    codigo_proyecto text,
    documento_cliente text,
    usuario_separacion text,
    tipo_unidad_principal text,
    estado_separacion text,
    separacion_source_id bigint,
    fecha_separacion_raw date,
    fecha_entrada_stock date,
    fecha_separacion_analitica date,
    fecha_separacion_ajustada boolean NOT NULL DEFAULT false,
    motivo_ajuste_fecha text,

    datos_extras_fecha_minuta_id bigint,
    fecha_de_minuta_raw text,
    fecha_de_minuta date,
    pago_ci_raw text,
    pago_ci numeric,
    datos_extras_pago_ci_id bigint,
    fecha_pago_ci date,
    monto_total_pagado_raw text,
    monto_total_pagado numeric,
    monto_pagado_de_cuota_inicial_raw text,
    monto_pagado_de_cuota_inicial numeric,
    monto_pagado_cuota_inicial numeric,
    asesor_compartido text,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (codigo_proforma, codigo_unidad)
);

-- Backwards-compatible migration for already-created local tables.
ALTER TABLE analytics.int_proforma_minuta
    ADD COLUMN IF NOT EXISTS datos_extras_pago_ci_id bigint;
ALTER TABLE analytics.int_proforma_minuta
    ADD COLUMN IF NOT EXISTS fecha_pago_ci date;

CREATE TABLE IF NOT EXISTS analytics.int_ciclo_comercial_unidad (
    codigo_proforma text NOT NULL,
    codigo_unidad text NOT NULL,
    codigo_proyecto text,

    separacion_source_id bigint,
    fecha_entrada_stock date,
    fecha_separacion_raw date,
    fecha_separacion date,
    fecha_separacion_ajustada boolean NOT NULL DEFAULT false,

    venta_source_id bigint,
    fecha_firma_legacy date,
    datos_extras_fecha_minuta_id bigint,
    fecha_de_minuta date,
    fecha_venta date,
    metodo_fecha_venta text NOT NULL,
    datos_extras_pago_ci_id bigint,
    fecha_pago_ci date,

    primera_fecha_caida date,
    ultima_fecha_caida date,
    cantidad_anulaciones integer NOT NULL DEFAULT 0,

    resultado_ciclo text NOT NULL,
    dias_separacion_venta integer,
    dias_separacion_caida integer,

    documento_cliente text,
    asesor text,
    tipo_unidad_principal text,

    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (codigo_proforma, codigo_unidad)
);

-- Backwards-compatible migration for already-created local tables.
ALTER TABLE analytics.int_ciclo_comercial_unidad
    ADD COLUMN IF NOT EXISTS datos_extras_pago_ci_id bigint;
ALTER TABLE analytics.int_ciclo_comercial_unidad
    ADD COLUMN IF NOT EXISTS fecha_pago_ci date;

CREATE TABLE IF NOT EXISTS analytics.fact_movimientos_stock (
    movement_id text PRIMARY KEY,
    source_table text NOT NULL,
    source_id bigint,
    source_event_key text NOT NULL,

    codigo_proforma text,
    codigo_unidad text NOT NULL,
    codigo_proyecto text,

    fecha_evento date NOT NULL,
    tipo_evento text NOT NULL,
    event_order integer NOT NULL,

    estado_anterior text,
    estado_nuevo text,
    transition_applied boolean NOT NULL,
    transition_reason text,

    delta_stock integer NOT NULL DEFAULT 0,
    delta_separadas_activas integer NOT NULL DEFAULT 0,
    delta_ventas integer NOT NULL DEFAULT 0,
    delta_caidas integer NOT NULL DEFAULT 0,

    refreshed_at timestamptz NOT NULL DEFAULT now()
);
