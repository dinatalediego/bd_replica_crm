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
    proyecto text,
    fecha_cliente date,
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

CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_etapa
    ON analytics.marketing_audiencias (etapa_maxima);
CREATE INDEX IF NOT EXISTS idx_marketing_audiencias_flags
    ON analytics.marketing_audiencias (positiva, negativa_sin_avance, apto_entrega_externa);

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
    aptas_entrega_externa bigint NOT NULL
);

CREATE OR REPLACE VIEW analytics.v_marketing_positiva AS
SELECT
    nombres AS "Nombres",
    apellidos AS "Apellidos",
    celular AS "Telefono_Celular",
    email AS "Correo_electronico",
    medio_captacion,
    proyecto,
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
    proyecto,
    etapa_maxima,
    fecha_cliente,
    consentimiento_publicidad_verificado,
    apto_entrega_externa,
    actualizado_en
FROM analytics.marketing_audiencias
WHERE negativa_sin_avance
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
    etapa_maxima,
    exclusion_convertido,
    exclusion_contacto_invalido,
    exclusion_no_contactar,
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
        WHERE exclusion_convertido OR exclusion_contacto_invalido OR exclusion_no_contactar
    )::bigint AS exclusiones,
    count(*) FILTER (WHERE contacto_valido)::bigint AS contacto_valido,
    count(*) FILTER (WHERE apto_entrega_externa)::bigint AS aptas_entrega_externa,
    max(actualizado_en) AS actualizado_en
FROM analytics.marketing_audiencias;

COMMENT ON TABLE analytics.marketing_audiencias IS
'Mart local para LAL/RMKT. Se deriva de Medallio y no consulta Redshift directamente.';
COMMENT ON TABLE analytics.marketing_consentimientos IS
'Evidencia explícita de autorización publicitaria. El refresh no infiere consentimiento.';
COMMENT ON TABLE analytics.marketing_supresiones IS
'Personas que no deben activarse publicitariamente; se administra con evidencia autorizada.';
COMMENT ON COLUMN analytics.marketing_audiencias.apto_entrega_externa IS
'TRUE solo con contacto válido, consentimiento permitido y sin supresión activa.';
