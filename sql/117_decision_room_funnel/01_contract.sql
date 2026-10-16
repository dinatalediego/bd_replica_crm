CREATE SCHEMA IF NOT EXISTS analytics;

-- Funnel operativo por mes de EVENTO, no por cohorte.
-- No calcular tasas de conversión entre estas columnas sin un contrato de cohortes:
-- un lead de enero puede proformar/separar/minutar en meses posteriores.
CREATE OR REPLACE VIEW analytics.v_decision_room_funnel_monthly AS
WITH clientes AS (
    SELECT
        c.source_id,
        c.dq_documento_limpio,
        COALESCE(
            'doc:' || NULLIF(c.dq_documento_limpio, ''),
            'email:' || NULLIF(lower(c.dq_email_limpio), ''),
            'phone:' || NULLIF(c.dq_celular_limpio, ''),
            'source:' || NULLIF(c.source_id, ''),
            'hash:' || c.source_row_hash
        ) AS persona_key
    FROM staging.clientes_calidad c
),
cliente_keys AS (
    SELECT persona_key, 'source_id'::text AS key_type, source_id AS key_value
    FROM clientes
    WHERE NULLIF(source_id, '') IS NOT NULL

    UNION

    SELECT persona_key, 'documento'::text, dq_documento_limpio
    FROM clientes
    WHERE NULLIF(dq_documento_limpio, '') IS NOT NULL
),
lead_base AS (
    SELECT
        cp.id::text AS source_row_id,
        NULLIF(regexp_replace(cp.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(cp) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(cp) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(cp) ->> 'codigo_cliente', '')
        ) AS source_id,
        NULLIF(btrim(cp.codigo_proyecto::text), '') AS codigo_proyecto,
        cp.fecha_creacion::date AS fecha_lead
    FROM raw_cygnus.clientes_proyectos cp
    WHERE NULLIF(btrim(cp.codigo_proyecto::text), '') IS NOT NULL
      AND cp.fecha_creacion IS NOT NULL
),
lead_keys AS (
    SELECT source_row_id, 'source_id'::text AS key_type, source_id AS key_value
    FROM lead_base
    WHERE NULLIF(source_id, '') IS NOT NULL

    UNION ALL

    SELECT source_row_id, 'documento'::text, documento
    FROM lead_base
    WHERE NULLIF(documento, '') IS NOT NULL
),
lead_evidence AS (
    SELECT DISTINCT
        lk.source_row_id,
        ck.persona_key
    FROM lead_keys lk
    JOIN cliente_keys ck
      ON ck.key_type = lk.key_type
     AND ck.key_value = lk.key_value
),
lead_identity AS (
    SELECT
        source_row_id,
        min(persona_key) AS persona_key,
        count(DISTINCT persona_key)::bigint AS identity_candidates
    FROM lead_evidence
    GROUP BY source_row_id
),
leads_monthly AS (
    SELECT
        lb.codigo_proyecto,
        date_trunc('month', lb.fecha_lead::timestamp)::date AS periodo_mes,
        count(DISTINCT lb.source_row_id)::bigint AS leads,
        count(DISTINCT li.persona_key) FILTER (
            WHERE li.identity_candidates = 1
        )::bigint AS clientes_unicos,
        count(DISTINCT lb.source_row_id) FILTER (
            WHERE li.identity_candidates = 1
        )::bigint AS leads_identidad_mapeada,
        count(DISTINCT lb.source_row_id) FILTER (
            WHERE li.identity_candidates > 1
        )::bigint AS leads_identidad_ambigua
    FROM lead_base lb
    LEFT JOIN lead_identity li USING (source_row_id)
    GROUP BY lb.codigo_proyecto, date_trunc('month', lb.fecha_lead::timestamp)::date
),
proformas_monthly AS (
    SELECT
        NULLIF(btrim(pu.codigo_proyecto::text), '') AS codigo_proyecto,
        date_trunc('month', pu.fecha_creacion::timestamp)::date AS periodo_mes,
        count(DISTINCT NULLIF(btrim(pu.codigo_proforma::text), ''))::bigint AS proformas
    FROM raw_cygnus.proforma_unidad pu
    WHERE NULLIF(btrim(pu.codigo_proyecto::text), '') IS NOT NULL
      AND pu.fecha_creacion IS NOT NULL
      AND NULLIF(btrim(pu.codigo_proforma::text), '') IS NOT NULL
      AND EXISTS (
          SELECT 1
          FROM analytics.v_absorcion_ventas_unidad u
          WHERE u.codigo_unidad = pu.codigo_unidad::text
            AND u.codigo_proyecto = btrim(pu.codigo_proyecto::text)
      )
    GROUP BY
        NULLIF(btrim(pu.codigo_proyecto::text), ''),
        date_trunc('month', pu.fecha_creacion::timestamp)::date
),
separaciones_monthly AS (
    SELECT
        codigo_proyecto,
        periodo_mes,
        separaciones_brutas
    FROM analytics.agg_ventas_mensual
),
minutas_monthly AS (
    SELECT
        codigo_proyecto,
        periodo_mes,
        ventas_mes AS minutas,
        fecha_corte AS commercial_cutoff
    FROM analytics.comercial_proyecto_mes
    WHERE NOT mes_parcial
),
months AS (
    SELECT codigo_proyecto, periodo_mes FROM leads_monthly
    UNION
    SELECT codigo_proyecto, periodo_mes FROM proformas_monthly
    UNION
    SELECT codigo_proyecto, periodo_mes FROM separaciones_monthly
    UNION
    SELECT codigo_proyecto, periodo_mes FROM minutas_monthly
)
SELECT
    m.codigo_proyecto,
    m.periodo_mes,
    COALESCE(l.leads, 0)::bigint AS leads,
    COALESCE(l.clientes_unicos, 0)::bigint AS clientes_unicos,
    COALESCE(l.leads_identidad_mapeada, 0)::bigint AS leads_identidad_mapeada,
    COALESCE(l.leads_identidad_ambigua, 0)::bigint AS leads_identidad_ambigua,
    GREATEST(
        COALESCE(l.leads, 0)
        - COALESCE(l.leads_identidad_mapeada, 0)
        - COALESCE(l.leads_identidad_ambigua, 0),
        0
    )::bigint AS leads_identidad_sin_match,
    CASE
        WHEN COALESCE(l.leads, 0) > 0
        THEN l.leads_identidad_mapeada::numeric / l.leads
    END AS identity_match_rate,
    COALESCE(p.proformas, 0)::bigint AS proformas,
    s.separaciones_brutas::bigint AS separaciones,
    v.minutas::bigint AS minutas,
    v.commercial_cutoff,
    'EVENT_MONTH_NOT_COHORT'::text AS funnel_semantics
FROM months m
LEFT JOIN leads_monthly l USING (codigo_proyecto, periodo_mes)
LEFT JOIN proformas_monthly p USING (codigo_proyecto, periodo_mes)
LEFT JOIN separaciones_monthly s USING (codigo_proyecto, periodo_mes)
LEFT JOIN minutas_monthly v USING (codigo_proyecto, periodo_mes);

COMMENT ON VIEW analytics.v_decision_room_funnel_monthly IS
'Funnel agregado proyecto-mes para Sala de decisiones: leads, clientes únicos con identidad gobernada, proformas residenciales, separaciones brutas y minutas gobernadas. Las etapas están fechadas por su propio mes de evento; no son una cohorte y no deben dividirse entre sí como tasas de conversión.';
