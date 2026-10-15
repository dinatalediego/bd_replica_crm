CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.marketing_consentimientos (
    persona_key text PRIMARY KEY,
    permitido boolean NOT NULL,
    fuente_verificacion text NOT NULL,
    verificado_en timestamptz NOT NULL,
    vence_en timestamptz,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    CHECK (vence_en IS NULL OR vence_en > verificado_en)
);

CREATE TABLE IF NOT EXISTS analytics.marketing_supresiones (
    persona_key text PRIMARY KEY,
    motivo text NOT NULL,
    activo boolean NOT NULL DEFAULT true,
    registrado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.marketing_audiencias (
    persona_key text PRIMARY KEY,
    source_id text,
    nombres text,
    apellidos text,
    celular text,
    email text,

    medio_captacion text,
    medio_captacion_cliente text,
    medio_captacion_origen text,

    codigo_proyecto_origen text,
    proyecto_origen text,
    codigo_proyecto_proforma text,
    proyecto_proforma text,
    codigo_proyecto_conversion text,
    proyecto_conversion text,

    proyecto text,
    fuente_proyecto text,
    cambio_proyecto boolean NOT NULL DEFAULT false,

    fecha_cliente date,
    fecha_cliente_crm date,
    fecha_origen_primario date,
    fecha_proforma timestamptz,
    fecha_separacion timestamptz,
    fecha_minuta_venta timestamptz,
    fecha_ultimo_avance timestamptz,

    etapa_maxima text NOT NULL CHECK (
        etapa_maxima IN ('sin_avance', 'proforma', 'separacion', 'minuta_venta')
    ),
    positiva boolean NOT NULL,
    negativa_sin_avance boolean NOT NULL,
    exclusion_convertido boolean NOT NULL,
    exclusion_contacto_invalido boolean NOT NULL,
    exclusion_no_contactar boolean NOT NULL,
    contacto_valido boolean NOT NULL,
    consentimiento_publicidad_verificado boolean NOT NULL,
    apto_entrega_externa boolean NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);

-- Upgrade idempotente para instalaciones existentes.
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS medio_captacion_cliente text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS medio_captacion_origen text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS codigo_proyecto_origen text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS proyecto_origen text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS codigo_proyecto_proforma text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS proyecto_proforma text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS codigo_proyecto_conversion text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS proyecto_conversion text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS fuente_proyecto text;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS cambio_proyecto boolean NOT NULL DEFAULT false;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS fecha_cliente_crm date;
ALTER TABLE analytics.marketing_audiencias
    ADD COLUMN IF NOT EXISTS fecha_origen_primario date;

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_etapa
    ON analytics.marketing_audiencias (etapa_maxima);

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_flags
    ON analytics.marketing_audiencias (
        positiva, negativa_sin_avance, apto_entrega_externa
    );

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_origen
    ON analytics.marketing_audiencias (
        codigo_proyecto_origen, fecha_origen_primario, medio_captacion
    );

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_conversion
    ON analytics.marketing_audiencias (
        codigo_proyecto_conversion, cambio_proyecto
    );

CREATE TABLE IF NOT EXISTS analytics.marketing_audiencias_proyectos (
    persona_key text NOT NULL
        REFERENCES analytics.marketing_audiencias(persona_key) ON DELETE CASCADE,
    codigo_proyecto text NOT NULL,
    proyecto text,

    fecha_primer_lead date,
    fecha_ultimo_lead date,
    medio_captacion_primer_touch text,
    medio_captacion_ultimo_touch text,
    cantidad_leads bigint NOT NULL DEFAULT 0,

    es_primer_touch boolean NOT NULL DEFAULT false,
    es_ultimo_touch boolean NOT NULL DEFAULT false,

    tuvo_proforma boolean NOT NULL DEFAULT false,
    tuvo_separacion boolean NOT NULL DEFAULT false,
    tuvo_minuta_venta boolean NOT NULL DEFAULT false,

    fecha_primera_proforma timestamptz,
    fecha_primera_separacion timestamptz,
    fecha_primera_minuta_venta timestamptz,

    actualizado_en timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (persona_key, codigo_proyecto)
);

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_proyectos_project
    ON analytics.marketing_audiencias_proyectos (
        codigo_proyecto, fecha_primer_lead
    );

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_proyectos_flags
    ON analytics.marketing_audiencias_proyectos (
        es_primer_touch, tuvo_proforma, tuvo_separacion, tuvo_minuta_venta
    );

CREATE TABLE IF NOT EXISTS analytics.marketing_audiencias_refresh_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    inactivity_days integer NOT NULL CHECK (inactivity_days > 0),
    personas bigint NOT NULL,
    positivas bigint NOT NULL,
    negativas_sin_avance bigint NOT NULL,
    exclusiones bigint NOT NULL,
    contacto_valido bigint NOT NULL,
    aptas_entrega_externa bigint NOT NULL,
    con_proyecto_origen bigint NOT NULL DEFAULT 0,
    con_proyecto_conversion bigint NOT NULL DEFAULT 0,
    cambios_proyecto bigint NOT NULL DEFAULT 0,
    project_links bigint NOT NULL DEFAULT 0
);

ALTER TABLE analytics.marketing_audiencias_refresh_runs
    ADD COLUMN IF NOT EXISTS con_proyecto_origen bigint NOT NULL DEFAULT 0;
ALTER TABLE analytics.marketing_audiencias_refresh_runs
    ADD COLUMN IF NOT EXISTS con_proyecto_conversion bigint NOT NULL DEFAULT 0;
ALTER TABLE analytics.marketing_audiencias_refresh_runs
    ADD COLUMN IF NOT EXISTS cambios_proyecto bigint NOT NULL DEFAULT 0;
ALTER TABLE analytics.marketing_audiencias_refresh_runs
    ADD COLUMN IF NOT EXISTS project_links bigint NOT NULL DEFAULT 0;

CREATE OR REPLACE VIEW analytics.v_marketing_positiva AS
SELECT
    nombres AS "Nombres",
    apellidos AS "Apellidos",
    celular AS "Telefono_Celular",
    email AS "Correo_electronico",

    medio_captacion,
    medio_captacion_cliente,
    medio_captacion_origen,

    codigo_proyecto_origen,
    proyecto_origen,
    codigo_proyecto_proforma,
    proyecto_proforma,
    codigo_proyecto_conversion,
    proyecto_conversion,
    proyecto,
    fuente_proyecto,
    cambio_proyecto,

    fecha_cliente,
    fecha_cliente_crm,
    fecha_origen_primario,
    etapa_maxima,
    fecha_ultimo_avance,

    consentimiento_publicidad_verificado,
    apto_entrega_externa,
    actualizado_en
FROM analytics.marketing_audiencias
WHERE positiva
  AND contacto_valido
  AND NOT exclusion_no_contactar;

CREATE OR REPLACE VIEW analytics.v_marketing_negativa_sin_avance AS
SELECT
    nombres AS "Nombres",
    apellidos AS "Apellidos",
    celular AS "Telefono_Celular",
    email AS "Correo_electronico",

    medio_captacion,
    medio_captacion_cliente,
    medio_captacion_origen,

    codigo_proyecto_origen,
    proyecto_origen,
    codigo_proyecto_proforma,
    proyecto_proforma,
    codigo_proyecto_conversion,
    proyecto_conversion,
    proyecto,
    fuente_proyecto,
    cambio_proyecto,

    fecha_cliente,
    fecha_cliente_crm,
    fecha_origen_primario,
    etapa_maxima,

    consentimiento_publicidad_verificado,
    apto_entrega_externa,
    actualizado_en
FROM analytics.marketing_audiencias
WHERE negativa_sin_avance
  AND contacto_valido
  AND NOT exclusion_no_contactar;

CREATE OR REPLACE VIEW analytics.v_marketing_neutral_reciente AS
SELECT
    nombres AS "Nombres",
    apellidos AS "Apellidos",
    celular AS "Telefono_Celular",
    email AS "Correo_electronico",

    medio_captacion,
    medio_captacion_cliente,
    medio_captacion_origen,

    codigo_proyecto_origen,
    proyecto_origen,
    codigo_proyecto_proforma,
    proyecto_proforma,
    codigo_proyecto_conversion,
    proyecto_conversion,
    proyecto,
    fuente_proyecto,
    cambio_proyecto,

    fecha_cliente,
    fecha_cliente_crm,
    fecha_origen_primario,
    etapa_maxima,

    consentimiento_publicidad_verificado,
    apto_entrega_externa,
    actualizado_en
FROM analytics.marketing_audiencias
WHERE NOT positiva
  AND NOT negativa_sin_avance
  AND contacto_valido
  AND NOT exclusion_no_contactar;

CREATE OR REPLACE VIEW analytics.v_marketing_exclusiones AS
SELECT
    nombres AS "Nombres",
    apellidos AS "Apellidos",
    celular AS "Telefono_Celular",
    email AS "Correo_electronico",
    medio_captacion,
    proyecto,
    proyecto_origen,
    proyecto_conversion,
    etapa_maxima,
    exclusion_convertido,
    exclusion_contacto_invalido,
    exclusion_no_contactar,
    consentimiento_publicidad_verificado,
    apto_entrega_externa,
    actualizado_en
FROM analytics.marketing_audiencias
WHERE exclusion_convertido
   OR exclusion_contacto_invalido
   OR exclusion_no_contactar;

CREATE OR REPLACE VIEW analytics.v_marketing_audiencias_health AS
SELECT
    count(*)::bigint AS personas,
    count(*) FILTER (WHERE positiva)::bigint AS positivas,
    count(*) FILTER (WHERE negativa_sin_avance)::bigint AS negativas_sin_avance,
    count(*) FILTER (
        WHERE exclusion_convertido
           OR exclusion_contacto_invalido
           OR exclusion_no_contactar
    )::bigint AS exclusiones,
    count(*) FILTER (WHERE contacto_valido)::bigint AS contacto_valido,
    count(*) FILTER (WHERE apto_entrega_externa)::bigint AS aptas_entrega_externa,

    count(*) FILTER (
        WHERE codigo_proyecto_origen IS NOT NULL
    )::bigint AS con_proyecto_origen,

    count(*) FILTER (
        WHERE codigo_proyecto_conversion IS NOT NULL
    )::bigint AS con_proyecto_conversion,

    count(*) FILTER (
        WHERE cambio_proyecto
    )::bigint AS cambios_proyecto,

    (
        SELECT count(*)::bigint
        FROM analytics.marketing_audiencias_proyectos
    ) AS project_links,

    max(actualizado_en) AS actualizado_en
FROM analytics.marketing_audiencias;

COMMENT ON TABLE analytics.marketing_audiencias IS
'Mart local persona-level para LAL/RMKT. Resuelve medio/proyecto con prioridad de origen sin perder proforma ni conversión.';

COMMENT ON TABLE analytics.marketing_audiencias_proyectos IS
'Linaje multi-proyecto por persona: captación, proforma, separación y venta/minuta sin colapsar a un único proyecto.';

COMMENT ON TABLE analytics.marketing_consentimientos IS
'Evidencia explícita de autorización publicitaria. El refresh no infiere consentimiento.';

COMMENT ON TABLE analytics.marketing_supresiones IS
'Personas que no deben activarse publicitariamente; se administra con evidencia autorizada.';

COMMENT ON COLUMN analytics.marketing_audiencias.proyecto IS
'Proyecto analítico resuelto con prioridad ORIGEN > CONVERSION > PROFORMA > CLIENTE.';

COMMENT ON COLUMN analytics.marketing_audiencias.fuente_proyecto IS
'Fuente que gobernó proyecto: ORIGEN, CONVERSION, PROFORMA, CLIENTE o SIN_PROYECTO.';

COMMENT ON COLUMN analytics.marketing_audiencias.cambio_proyecto IS
'TRUE cuando el proyecto de origen difiere del proyecto de conversión; usa proforma como fallback si aún no existe conversión.';

COMMENT ON COLUMN analytics.marketing_audiencias.apto_entrega_externa IS
'TRUE solo con contacto válido, consentimiento permitido y sin supresión activa.';
