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

-- Auditoría de identidad y semántica de la fuente de captación.
-- No expone documentos; solo agregados de calidad y repetición.
CREATE OR REPLACE VIEW analytics.v_decision_room_identity_audit_monthly AS
WITH lead_base AS (
    SELECT
        cp.id::text AS source_row_id,
        NULLIF(regexp_replace(cp.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        NULLIF(btrim(cp.codigo_proyecto::text), '') AS codigo_proyecto,
        date_trunc('month', cp.fecha_creacion::timestamp)::date AS periodo_mes
    FROM raw_cygnus.clientes_proyectos cp
    WHERE NULLIF(btrim(cp.codigo_proyecto::text), '') IS NOT NULL
      AND cp.fecha_creacion IS NOT NULL
),
project_document_frequency AS (
    SELECT
        codigo_proyecto,
        documento,
        count(*)::bigint AS registros_persona_proyecto
    FROM lead_base
    WHERE documento IS NOT NULL
    GROUP BY codigo_proyecto, documento
),
document_project_scope AS (
    SELECT
        documento,
        count(DISTINCT codigo_proyecto)::bigint AS proyectos_distintos
    FROM lead_base
    WHERE documento IS NOT NULL
    GROUP BY documento
),
monthly_raw AS (
    SELECT
        lb.codigo_proyecto,
        lb.periodo_mes,
        count(*)::bigint AS source_rows,
        count(DISTINCT lb.source_row_id)::bigint AS distinct_lead_ids,
        count(*) FILTER (WHERE lb.documento IS NULL)::bigint AS rows_without_document,
        count(DISTINCT lb.documento)::bigint AS distinct_documents,
        GREATEST(count(*) - count(DISTINCT lb.source_row_id), 0)::bigint AS duplicate_id_rows,
        GREATEST(
            count(*) FILTER (WHERE lb.documento IS NOT NULL)
            - count(DISTINCT lb.documento),
            0
        )::bigint AS duplicate_document_rows_within_month,
        count(*) FILTER (
            WHERE COALESCE(pdf.registros_persona_proyecto, 0) > 1
        )::bigint AS repeated_person_project_rows,
        count(DISTINCT lb.documento) FILTER (
            WHERE COALESCE(dps.proyectos_distintos, 0) > 1
        )::bigint AS multi_project_documents
    FROM lead_base lb
    LEFT JOIN project_document_frequency pdf
      ON pdf.codigo_proyecto = lb.codigo_proyecto
     AND pdf.documento = lb.documento
    LEFT JOIN document_project_scope dps
      ON dps.documento = lb.documento
    GROUP BY lb.codigo_proyecto, lb.periodo_mes
)
SELECT
    r.codigo_proyecto,
    r.periodo_mes,
    r.source_rows,
    r.distinct_lead_ids,
    r.rows_without_document,
    r.distinct_documents,
    r.duplicate_id_rows,
    r.duplicate_document_rows_within_month,
    r.repeated_person_project_rows,
    r.multi_project_documents,
    f.leads_identidad_mapeada AS mapped_leads,
    f.leads_identidad_ambigua AS ambiguous_leads,
    f.leads_identidad_sin_match AS unmatched_leads,
    f.clientes_unicos AS unique_clients,
    f.identity_match_rate,
    CASE
        WHEN r.repeated_person_project_rows = 0
         AND r.duplicate_document_rows_within_month = 0
        THEN 'PERSON_PROJECT_ENTRY_LIKE'
        ELSE 'MULTI_EVENT_LEAD_LIKE'
    END AS source_semantics,
    CASE
        WHEN COALESCE(f.leads_identidad_ambigua, 0) > 0 THEN 'FAIL'
        WHEN COALESCE(f.leads_identidad_sin_match, 0) > 0
          OR r.duplicate_id_rows > 0 THEN 'WARN'
        ELSE 'PASS'
    END AS identity_audit_status
FROM monthly_raw r
LEFT JOIN analytics.v_decision_room_funnel_monthly f
  USING (codigo_proyecto, periodo_mes);

COMMENT ON VIEW analytics.v_decision_room_identity_audit_monthly IS
'Auditoría agregada de identidad para la Sala. Clasifica si clientes_proyectos se comporta como entrada persona-proyecto o como tabla multi-evento; no expone identificadores personales.';

-- Funnel de cohortes reales: el denominador es la persona captada en T para ese proyecto.
-- Las conversiones se observan solo si el evento ocurre en el futuro respecto al lead.
-- Las tasas realized_as_of están censuradas para cohortes recientes; por eso también se
-- publican ventanas comparables de 30/60/90 días con denominador maduro.
CREATE OR REPLACE VIEW analytics.v_decision_room_funnel_cohort_monthly AS
WITH clock AS (
    SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date AS as_of_date
),
base AS (
    SELECT
        map.persona_key,
        map.codigo_proyecto,
        map.fecha_primer_lead::date AS lead_date,
        date_trunc('month', map.fecha_primer_lead::timestamp)::date AS cohort_month,
        map.fecha_primera_proforma::date AS proforma_date,
        map.fecha_primera_separacion::date AS separation_date,
        map.fecha_primera_minuta_venta::date AS minuta_date,
        c.as_of_date
    FROM analytics.marketing_audiencias_proyectos map
    CROSS JOIN clock c
    WHERE map.fecha_primer_lead IS NOT NULL
),
flags AS (
    SELECT
        b.*,
        (b.proforma_date IS NOT NULL AND b.proforma_date >= b.lead_date) AS proforma_future,
        (b.separation_date IS NOT NULL AND b.separation_date >= b.lead_date) AS separation_future,
        (b.minuta_date IS NOT NULL AND b.minuta_date >= b.lead_date) AS minuta_future,
        (
            (b.proforma_date IS NOT NULL AND b.proforma_date < b.lead_date)
            OR (b.separation_date IS NOT NULL AND b.separation_date < b.lead_date)
            OR (b.minuta_date IS NOT NULL AND b.minuta_date < b.lead_date)
            OR (
                b.proforma_date IS NOT NULL AND b.separation_date IS NOT NULL
                AND b.separation_date < b.proforma_date
            )
            OR (
                b.separation_date IS NOT NULL AND b.minuta_date IS NOT NULL
                AND b.minuta_date < b.separation_date
            )
        ) AS temporal_anomaly
    FROM base b
),
agg AS (
    SELECT
        codigo_proyecto,
        cohort_month,
        max(as_of_date) AS as_of_date,
        count(*)::bigint AS cohort_leads,
        count(DISTINCT persona_key)::bigint AS cohort_unique_clients,
        count(*) FILTER (WHERE proforma_future)::bigint AS proformas_realized,
        count(*) FILTER (WHERE separation_future)::bigint AS separaciones_realized,
        count(*) FILTER (WHERE minuta_future)::bigint AS minutas_realized,
        count(*) FILTER (WHERE temporal_anomaly)::bigint AS temporal_anomaly_rows,
        avg((proforma_date - lead_date)::numeric) FILTER (WHERE proforma_future)
            AS avg_days_to_proforma,
        avg((separation_date - lead_date)::numeric) FILTER (WHERE separation_future)
            AS avg_days_to_separacion,
        avg((minuta_date - lead_date)::numeric) FILTER (WHERE minuta_future)
            AS avg_days_to_minuta,

        count(*) FILTER (WHERE lead_date <= as_of_date - 30)::bigint AS eligible_30d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 30
              AND proforma_future AND proforma_date <= lead_date + 30
        )::bigint AS proformas_30d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 30
              AND separation_future AND separation_date <= lead_date + 30
        )::bigint AS separaciones_30d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 30
              AND minuta_future AND minuta_date <= lead_date + 30
        )::bigint AS minutas_30d,

        count(*) FILTER (WHERE lead_date <= as_of_date - 60)::bigint AS eligible_60d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 60
              AND proforma_future AND proforma_date <= lead_date + 60
        )::bigint AS proformas_60d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 60
              AND separation_future AND separation_date <= lead_date + 60
        )::bigint AS separaciones_60d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 60
              AND minuta_future AND minuta_date <= lead_date + 60
        )::bigint AS minutas_60d,

        count(*) FILTER (WHERE lead_date <= as_of_date - 90)::bigint AS eligible_90d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 90
              AND proforma_future AND proforma_date <= lead_date + 90
        )::bigint AS proformas_90d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 90
              AND separation_future AND separation_date <= lead_date + 90
        )::bigint AS separaciones_90d,
        count(*) FILTER (
            WHERE lead_date <= as_of_date - 90
              AND minuta_future AND minuta_date <= lead_date + 90
        )::bigint AS minutas_90d
    FROM flags
    GROUP BY codigo_proyecto, cohort_month
)
SELECT
    a.*,
    CASE WHEN cohort_unique_clients > 0
         THEN proformas_realized::numeric / cohort_unique_clients END
        AS lead_to_proforma_realized_rate,
    CASE WHEN cohort_unique_clients > 0
         THEN separaciones_realized::numeric / cohort_unique_clients END
        AS lead_to_separacion_realized_rate,
    CASE WHEN cohort_unique_clients > 0
         THEN minutas_realized::numeric / cohort_unique_clients END
        AS lead_to_minuta_realized_rate,

    CASE WHEN eligible_30d > 0 THEN proformas_30d::numeric / eligible_30d END
        AS lead_to_proforma_30d_rate,
    CASE WHEN eligible_30d > 0 THEN separaciones_30d::numeric / eligible_30d END
        AS lead_to_separacion_30d_rate,
    CASE WHEN eligible_30d > 0 THEN minutas_30d::numeric / eligible_30d END
        AS lead_to_minuta_30d_rate,

    CASE WHEN eligible_60d > 0 THEN proformas_60d::numeric / eligible_60d END
        AS lead_to_proforma_60d_rate,
    CASE WHEN eligible_60d > 0 THEN separaciones_60d::numeric / eligible_60d END
        AS lead_to_separacion_60d_rate,
    CASE WHEN eligible_60d > 0 THEN minutas_60d::numeric / eligible_60d END
        AS lead_to_minuta_60d_rate,

    CASE WHEN eligible_90d > 0 THEN proformas_90d::numeric / eligible_90d END
        AS lead_to_proforma_90d_rate,
    CASE WHEN eligible_90d > 0 THEN separaciones_90d::numeric / eligible_90d END
        AS lead_to_separacion_90d_rate,
    CASE WHEN eligible_90d > 0 THEN minutas_90d::numeric / eligible_90d END
        AS lead_to_minuta_90d_rate,

    CASE WHEN temporal_anomaly_rows = 0 THEN 'PASS' ELSE 'WARN' END AS cohort_quality_status,
    'LEAD_COHORT_REALIZED_AS_OF_CUTOFF'::text AS cohort_semantics
FROM agg a;

COMMENT ON VIEW analytics.v_decision_room_funnel_cohort_monthly IS
'Funnel de cohortes reales por proyecto y mes de captación: cada persona-proyecto se ancla en fecha_primer_lead y solo cuenta proforma/separación/minuta posterior. Publica tasas realizadas censuradas y tasas maduras a 30/60/90 días.';
