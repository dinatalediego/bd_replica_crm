CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS staging.portal_leads_base (
    lead_uid                    text PRIMARY KEY,
    fuente_lead                 text NOT NULL CHECK (fuente_lead IN ('ORIGEN', 'MEDIO_ACTUAL')),
    source_id                   text,
    codigo_proyecto             text,
    documento_cliente           text,
    fecha_creacion              timestamp,
    fecha_actualizacion         timestamp,
    canal_entrada               text,
    medio_captacion             text,
    nivel_interes               text,
    fecha_asignacion            timestamp,
    vendedor_asignado           text,
    tipo_interaccion            text,
    nombre_interaccion          text,
    segmento                    text,
    utm_source                  text,
    utm_medium                  text,
    cliente_source_id           text,
    nombres                     text,
    apellidos                   text,
    nombre_completo             text,
    dni                         text,
    celular                     text,
    email                       text,
    medio_cliente               text,
    person_key                  text,
    duplicado_en_origen         boolean NOT NULL DEFAULT false,
    lead_origen_uid             text,
    incluir_en_kpi              boolean NOT NULL DEFAULT true,
    refreshed_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portal_leads_fecha
    ON staging.portal_leads_base (fecha_creacion);
CREATE INDEX IF NOT EXISTS idx_portal_leads_medio
    ON staging.portal_leads_base (lower(medio_captacion));
CREATE INDEX IF NOT EXISTS idx_portal_leads_person
    ON staging.portal_leads_base (person_key);
CREATE INDEX IF NOT EXISTS idx_portal_leads_fuente
    ON staging.portal_leads_base (fuente_lead, incluir_en_kpi);

CREATE TABLE IF NOT EXISTS staging.portal_compradores_base (
    conversion_uid              text PRIMARY KEY,
    conversion_key              text NOT NULL UNIQUE,
    proceso_id                  text,
    codigo_proyecto             text,
    nombre_proyecto             text,
    codigo_unidad               text,
    codigo_proforma             text,
    documento_cliente           text,
    fecha_separacion            timestamp NOT NULL,
    nombres                     text,
    apellidos                   text,
    nombre_completo             text,
    dni                         text,
    celular                     text,
    email                       text,
    medio_cliente               text,
    person_key                  text,
    filas_proceso_deduplicadas  integer NOT NULL DEFAULT 1,
    refreshed_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portal_compradores_fecha
    ON staging.portal_compradores_base (fecha_separacion);
CREATE INDEX IF NOT EXISTS idx_portal_compradores_dni
    ON staging.portal_compradores_base (dni);
CREATE INDEX IF NOT EXISTS idx_portal_compradores_person
    ON staging.portal_compradores_base (person_key);

CREATE TABLE IF NOT EXISTS analytics.portal_lead_match (
    lead_uid                    text PRIMARY KEY,
    conversion_uid              text,
    conversion_key              text,
    estado_match                text NOT NULL CHECK (estado_match IN ('CONFIRMADO', 'PROBABLE', 'REVISAR', 'NO MATCH')),
    criterio_match              text,
    score_global                numeric(6,2) NOT NULL DEFAULT 0,
    score_dni                   numeric(6,2) NOT NULL DEFAULT 0,
    score_nombre                numeric(6,2) NOT NULL DEFAULT 0,
    score_celular               numeric(6,2) NOT NULL DEFAULT 0,
    score_email                 numeric(6,2) NOT NULL DEFAULT 0,
    fecha_separacion            timestamp,
    dias_a_separacion           integer,
    conversion_elegible         boolean NOT NULL DEFAULT false,
    conversion_atribuida        boolean NOT NULL DEFAULT false,
    motivo_atribucion           text,
    refreshed_at                timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portal_match_conversion
    ON analytics.portal_lead_match (conversion_key, conversion_atribuida);
CREATE INDEX IF NOT EXISTS idx_portal_match_estado
    ON analytics.portal_lead_match (estado_match);

CREATE OR REPLACE VIEW analytics.v_portal_conversion_export AS
SELECT
    l.lead_uid,
    l.fuente_lead,
    l.source_id,
    l.codigo_proyecto AS proyecto_lead,
    l.documento_cliente AS documento_lead_fuente,
    l.fecha_creacion,
    l.fecha_actualizacion,
    l.canal_entrada,
    l.medio_captacion,
    l.nivel_interes,
    l.fecha_asignacion,
    l.vendedor_asignado,
    l.tipo_interaccion,
    l.nombre_interaccion,
    l.segmento,
    l.utm_source,
    l.utm_medium,
    l.nombres AS nombres_lead,
    l.apellidos AS apellidos_lead,
    l.nombre_completo AS nombre_lead,
    l.dni AS dni_lead,
    l.celular AS celular_lead,
    l.email AS email_lead,
    l.medio_cliente AS medio_cliente_lead,
    l.duplicado_en_origen,
    l.lead_origen_uid,
    l.incluir_en_kpi,
    m.estado_match,
    m.criterio_match,
    m.score_global,
    m.score_dni,
    m.score_nombre,
    m.score_celular,
    m.score_email,
    m.conversion_elegible,
    m.conversion_atribuida,
    m.motivo_atribucion,
    m.dias_a_separacion,
    b.conversion_key,
    b.fecha_separacion,
    b.documento_cliente AS documento_comprador_fuente,
    b.dni AS dni_comprador,
    b.nombre_completo AS nombre_comprador,
    b.celular AS celular_comprador,
    b.email AS email_comprador,
    b.medio_cliente AS medio_cliente_comprador,
    b.codigo_proyecto AS proyecto_conversion,
    b.nombre_proyecto AS nombre_proyecto_conversion,
    b.codigo_unidad,
    b.codigo_proforma,
    b.filas_proceso_deduplicadas,
    extract(year FROM l.fecha_creacion)::integer AS lead_year,
    date_trunc('month', l.fecha_creacion)::date AS lead_month
FROM staging.portal_leads_base l
LEFT JOIN analytics.portal_lead_match m USING (lead_uid)
LEFT JOIN staging.portal_compradores_base b
  ON b.conversion_uid = m.conversion_uid;

CREATE OR REPLACE VIEW analytics.v_portal_conversion_medio AS
SELECT
    extract(year FROM l.fecha_creacion)::integer AS lead_year,
    l.fuente_lead,
    coalesce(nullif(lower(btrim(l.medio_captacion)), ''), '(sin medio)') AS medio_captacion,
    count(*) FILTER (WHERE l.incluir_en_kpi) AS leads,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.estado_match = 'CONFIRMADO') AS matches_confirmados,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.estado_match = 'PROBABLE') AS matches_probables,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida) AS conversiones,
    round(
        count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida)::numeric
        / nullif(count(*) FILTER (WHERE l.incluir_en_kpi), 0),
        6
    ) AS tasa_conversion,
    round(avg(m.dias_a_separacion) FILTER (WHERE m.conversion_atribuida), 2) AS dias_promedio_separacion,
    count(*) FILTER (WHERE l.duplicado_en_origen) AS duplicados_origen_excluidos
FROM staging.portal_leads_base l
LEFT JOIN analytics.portal_lead_match m USING (lead_uid)
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW analytics.v_portal_conversion_medio_total AS
SELECT
    extract(year FROM l.fecha_creacion)::integer AS lead_year,
    coalesce(nullif(lower(btrim(l.medio_captacion)), ''), '(sin medio)') AS medio_captacion,
    count(*) FILTER (WHERE l.incluir_en_kpi) AS leads,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida) AS conversiones,
    round(
        count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida)::numeric
        / nullif(count(*) FILTER (WHERE l.incluir_en_kpi), 0),
        6
    ) AS tasa_conversion,
    round(avg(m.dias_a_separacion) FILTER (WHERE m.conversion_atribuida), 2) AS dias_promedio_separacion,
    count(*) FILTER (WHERE l.incluir_en_kpi AND l.fuente_lead = 'ORIGEN') AS leads_origen,
    count(*) FILTER (WHERE l.incluir_en_kpi AND l.fuente_lead = 'MEDIO_ACTUAL') AS leads_medio_actual,
    count(*) FILTER (WHERE l.duplicado_en_origen) AS duplicados_origen_excluidos
FROM staging.portal_leads_base l
LEFT JOIN analytics.portal_lead_match m USING (lead_uid)
GROUP BY 1, 2;

CREATE OR REPLACE VIEW analytics.v_portal_conversion_cohorte_mensual AS
SELECT
    date_trunc('month', l.fecha_creacion)::date AS mes_lead,
    l.fuente_lead,
    coalesce(nullif(lower(btrim(l.medio_captacion)), ''), '(sin medio)') AS medio_captacion,
    count(*) FILTER (WHERE l.incluir_en_kpi) AS leads,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida) AS conversiones,
    round(
        count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida)::numeric
        / nullif(count(*) FILTER (WHERE l.incluir_en_kpi), 0),
        6
    ) AS tasa_conversion,
    round(avg(m.dias_a_separacion) FILTER (WHERE m.conversion_atribuida), 2) AS dias_promedio_separacion
FROM staging.portal_leads_base l
LEFT JOIN analytics.portal_lead_match m USING (lead_uid)
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW analytics.v_portal_conversion_proyecto AS
SELECT
    extract(year FROM l.fecha_creacion)::integer AS lead_year,
    l.fuente_lead,
    coalesce(nullif(lower(btrim(l.medio_captacion)), ''), '(sin medio)') AS medio_captacion,
    coalesce(nullif(btrim(l.codigo_proyecto), ''), '(sin proyecto)') AS codigo_proyecto,
    count(*) FILTER (WHERE l.incluir_en_kpi) AS leads,
    count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida) AS conversiones,
    round(
        count(*) FILTER (WHERE l.incluir_en_kpi AND m.conversion_atribuida)::numeric
        / nullif(count(*) FILTER (WHERE l.incluir_en_kpi), 0),
        6
    ) AS tasa_conversion,
    round(avg(m.dias_a_separacion) FILTER (WHERE m.conversion_atribuida), 2) AS dias_promedio_separacion
FROM staging.portal_leads_base l
LEFT JOIN analytics.portal_lead_match m USING (lead_uid)
GROUP BY 1, 2, 3, 4;

CREATE OR REPLACE VIEW analytics.v_portal_conversion_conversiones AS
SELECT
    b.*,
    l.lead_uid AS lead_atribuido_uid,
    l.fuente_lead AS fuente_atribuida,
    l.medio_captacion AS medio_atribuido,
    l.codigo_proyecto AS proyecto_lead_atribuido,
    l.fecha_creacion AS fecha_lead_atribuido,
    m.estado_match,
    m.score_global,
    m.dias_a_separacion
FROM staging.portal_compradores_base b
LEFT JOIN analytics.portal_lead_match m
  ON m.conversion_uid = b.conversion_uid
 AND m.conversion_atribuida
LEFT JOIN staging.portal_leads_base l USING (lead_uid);

CREATE OR REPLACE VIEW analytics.v_portal_conversion_health AS
SELECT
    (SELECT count(*) FROM staging.portal_leads_base) AS leads_total,
    (SELECT count(*) FROM staging.portal_leads_base WHERE fuente_lead = 'ORIGEN') AS leads_origen,
    (SELECT count(*) FROM staging.portal_leads_base WHERE fuente_lead = 'MEDIO_ACTUAL') AS leads_medio_actual,
    (SELECT count(*) FROM staging.portal_leads_base WHERE duplicado_en_origen) AS medio_actual_duplicado_en_origen,
    (SELECT count(*) FROM staging.portal_compradores_base) AS compradores_deduplicados,
    (SELECT count(*) FROM analytics.portal_lead_match WHERE estado_match = 'CONFIRMADO') AS matches_confirmados,
    (SELECT count(*) FROM analytics.portal_lead_match WHERE estado_match = 'PROBABLE') AS matches_probables,
    (SELECT count(*) FROM analytics.portal_lead_match WHERE estado_match = 'REVISAR') AS matches_revisar,
    (SELECT count(*) FROM analytics.portal_lead_match WHERE conversion_atribuida) AS conversiones_atribuidas,
    (
        SELECT count(*)
        FROM (
            SELECT conversion_key
            FROM analytics.portal_lead_match
            WHERE conversion_atribuida
            GROUP BY conversion_key
            HAVING count(*) > 1
        ) d
    ) AS conversiones_duplicadas_error,
    greatest(
        coalesce((SELECT max(refreshed_at) FROM staging.portal_leads_base), '-infinity'::timestamptz),
        coalesce((SELECT max(refreshed_at) FROM staging.portal_compradores_base), '-infinity'::timestamptz),
        coalesce((SELECT max(refreshed_at) FROM analytics.portal_lead_match), '-infinity'::timestamptz)
    ) AS refreshed_at;

COMMENT ON TABLE staging.portal_leads_base IS
'Leads ORIGEN (clientes_proyectos) y MEDIO_ACTUAL (interacciones/portal inmobiliario), enriquecidos con staging.clientes_calidad.';
COMMENT ON COLUMN staging.portal_leads_base.duplicado_en_origen IS
'Si el mismo lead aparece en ORIGEN y MEDIO_ACTUAL, ORIGEN gana; la fila actual se conserva solo para auditoria.';
COMMENT ON TABLE staging.portal_compradores_base IS
'Separaciones Activo deduplicadas por persona; DNI exacto de 8 digitos es la llave prioritaria.';
COMMENT ON TABLE analytics.portal_lead_match IS
'Cuatro controles de identidad, gate temporal y asignacion unica de cada conversion.';
