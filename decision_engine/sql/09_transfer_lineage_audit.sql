-- Audit reported department transfers against observable successor separations.
--
-- Purpose:
-- * distinguish a CRM-reported transfer from a lineage-verified continuation;
-- * verify, when possible, that the successor matches depa_del_cambio rather
--   than merely being any later separation for the same client;
-- * never use transfer/post-outcome evidence as a live feature;
-- * keep reported transfers excluded from binary training conservatively until
--   successor lineage is certified;
-- * surface evidence quality before any model training.
--
-- This file intentionally drops/recreates these views because the v2 audit adds
-- and reorders columns. PostgreSQL CREATE OR REPLACE VIEW cannot safely replace
-- an already-installed v1 view when the projected column layout changes.

DROP VIEW IF EXISTS decision_intelligence.v_department_transfer_lineage_health;
DROP VIEW IF EXISTS decision_intelligence.v_department_transfer_lineage_audit;

CREATE VIEW decision_intelligence.v_department_transfer_lineage_audit AS
WITH transfer_base AS (
    SELECT
        -- v_separation_fall_training_outcome already inherits the governed
        -- fall-reason fields from v_separation_fall_outcome_history. Do not
        -- rejoin/project them a second time: doing so creates duplicate column
        -- names (e.g. cambio_de_departamento) and makes the CTE ambiguous.
        t.*,
        regexp_replace(
            translate(lower(coalesce(t.depa_del_cambio, '')), 'áéíóúüñ', 'aeiouun'),
            '[^a-z0-9]+', '', 'g'
        ) AS declared_destination_norm
    FROM decision_intelligence.v_separation_fall_training_outcome t
    WHERE t.training_outcome_class = 'TRANSFER_UNIT'
)
SELECT
    t.separation_id,
    t.codigo_proforma,
    t.codigo_unidad,
    t.codigo_proyecto,
    t.documento_cliente,
    t.asesor,
    t.fecha_separacion,
    t.primera_fecha_caida,
    t.cambio_de_departamento,
    t.depa_del_cambio,
    t.motivo_caida_segun_asesor,
    true::boolean AS transfer_reported_in_crm,
    s.successor_codigo_proforma,
    s.successor_codigo_unidad,
    s.successor_codigo_proyecto,
    s.successor_nombre_unidad,
    s.successor_nombre_proyecto,
    s.successor_separacion_at,
    CASE
        WHEN s.successor_separacion_at IS NOT NULL
         AND t.primera_fecha_caida IS NOT NULL
        THEN (s.successor_separacion_at::date - t.primera_fecha_caida::date)::integer
        ELSE NULL::integer
    END AS days_to_successor_separation,
    nullif(t.declared_destination_norm, '') IS NOT NULL AS declared_destination_available,
    coalesce(s.destination_match_score, 0)::integer AS destination_match_score,
    CASE
        WHEN nullif(t.declared_destination_norm, '') IS NULL
            THEN 'NO_DECLARED_DESTINATION'
        WHEN s.successor_separacion_at IS NULL
            THEN 'NO_SUCCESSOR_TO_COMPARE'
        WHEN s.destination_match_score >= 3
            THEN 'DECLARED_UNIT_MATCH'
        WHEN s.destination_match_score = 2
            THEN 'PROJECT_AND_UNIT_NUMBER_MATCH'
        WHEN s.destination_match_score = 1
            THEN 'UNIT_NUMBER_ONLY_MATCH'
        ELSE 'DECLARED_DESTINATION_MISMATCH'
    END::text AS destination_match_status,
    CASE
        WHEN t.documento_cliente IS NULL THEN 'MISSING_CLIENT_KEY'
        WHEN s.successor_separacion_at IS NULL THEN 'REPORTED_NO_SUCCESSOR_WITHIN_90D'
        WHEN nullif(t.declared_destination_norm, '') IS NULL
         AND s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            THEN 'SUCCESSOR_WITHIN_30D_DESTINATION_UNVERIFIABLE'
        WHEN nullif(t.declared_destination_norm, '') IS NULL
            THEN 'SUCCESSOR_31_TO_90D_DESTINATION_UNVERIFIABLE'
        WHEN s.destination_match_score > 0
         AND s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            THEN 'VERIFIED_DESTINATION_WITHIN_30D'
        WHEN s.destination_match_score > 0
            THEN 'VERIFIED_DESTINATION_31_TO_90D'
        WHEN s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            THEN 'SUCCESSOR_WITHIN_30D_DESTINATION_MISMATCH'
        ELSE 'SUCCESSOR_31_TO_90D_DESTINATION_MISMATCH'
    END::text AS transfer_lineage_status,
    (s.successor_separacion_at IS NOT NULL) AS successor_lineage_observed,
    (
        s.successor_separacion_at IS NOT NULL
        AND s.destination_match_score > 0
        AND nullif(t.declared_destination_norm, '') IS NOT NULL
    ) AS declared_destination_lineage_verified,
    'POST_OUTCOME_AUDIT_ONLY'::text AS lineage_evidence_role,
    false::boolean AS lineage_live_feature_eligible
FROM transfer_base t
LEFT JOIN LATERAL (
    SELECT
        z.successor_codigo_proforma,
        z.successor_codigo_unidad,
        z.successor_codigo_proyecto,
        z.successor_nombre_unidad,
        z.successor_nombre_proyecto,
        z.successor_separacion_at,
        z.destination_match_score
    FROM (
        SELECT
            p.codigo_proforma::text AS successor_codigo_proforma,
            p.codigo_unidad::text AS successor_codigo_unidad,
            p.codigo_proyecto::text AS successor_codigo_proyecto,
            u.nombre_unidad::text AS successor_nombre_unidad,
            dp.nombre_proyecto::text AS successor_nombre_proyecto,
            p.fecha_inicio AS successor_separacion_at,
            p.id AS successor_source_id,
            CASE
                -- Strongest: declared text contains the canonical unit name.
                WHEN nullif(t.declared_destination_norm, '') IS NOT NULL
                 AND nullif(
                    regexp_replace(
                        translate(lower(coalesce(u.nombre_unidad::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                    ), ''
                 ) IS NOT NULL
                 AND t.declared_destination_norm LIKE '%' || regexp_replace(
                        translate(lower(coalesce(u.nombre_unidad::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                     ) || '%'
                    THEN 3

                -- Strong: project name plus numeric portion of unit agree.
                WHEN nullif(t.declared_destination_norm, '') IS NOT NULL
                 AND nullif(
                    regexp_replace(
                        translate(lower(coalesce(dp.nombre_proyecto::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                    ), ''
                 ) IS NOT NULL
                 AND t.declared_destination_norm LIKE '%' || regexp_replace(
                        translate(lower(coalesce(dp.nombre_proyecto::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                     ) || '%'
                 AND length(regexp_replace(coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g')) >= 2
                 AND t.declared_destination_norm LIKE '%' || regexp_replace(
                        coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g'
                     ) || '%'
                    THEN 2

                -- Weak but useful for abbreviated CRM destinations such as E-B24.
                WHEN nullif(t.declared_destination_norm, '') IS NOT NULL
                 AND length(regexp_replace(coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g')) >= 2
                 AND t.declared_destination_norm LIKE '%' || regexp_replace(
                        coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g'
                     ) || '%'
                    THEN 1
                ELSE 0
            END::integer AS destination_match_score
        FROM raw_cygnus.procesos p
        LEFT JOIN core.dim_unidad u
          ON u.codigo_unidad = p.codigo_unidad::text
        LEFT JOIN core.dim_proyecto dp
          ON dp.codigo_proyecto = p.codigo_proyecto::text
        WHERE lower(coalesce(p.nombre::text, '')) = 'separacion'
          AND p.documento_cliente::text = t.documento_cliente::text
          AND p.codigo_proforma IS NOT NULL
          AND p.codigo_proforma::text <> t.codigo_proforma
          AND p.fecha_inicio IS NOT NULL
          AND t.primera_fecha_caida IS NOT NULL
          AND p.fecha_inicio::date >= t.primera_fecha_caida::date
          AND p.fecha_inicio::date <= t.primera_fecha_caida::date + 90
          AND coalesce(p.nombre_flujo::text, '') <> 'Desistimiento de visita'
    ) z
    ORDER BY
        -- When CRM names a destination, prefer a matching successor over an
        -- unrelated earlier same-client separation. Without destination text,
        -- preserve chronological-first semantics.
        CASE WHEN nullif(t.declared_destination_norm, '') IS NOT NULL
             THEN z.destination_match_score ELSE 0 END DESC,
        z.successor_separacion_at,
        z.successor_source_id
    LIMIT 1
) s ON true;

CREATE VIEW decision_intelligence.v_department_transfer_lineage_health AS
SELECT
    count(*)::bigint AS reported_transfer_rows,
    count(*) FILTER (WHERE successor_lineage_observed)::bigint AS transfers_with_any_successor_90d,
    count(*) FILTER (WHERE declared_destination_lineage_verified)::bigint AS transfers_with_verified_destination_90d,
    count(*) FILTER (WHERE transfer_lineage_status = 'VERIFIED_DESTINATION_WITHIN_30D')::bigint AS verified_destination_within_30d,
    count(*) FILTER (WHERE transfer_lineage_status = 'VERIFIED_DESTINATION_31_TO_90D')::bigint AS verified_destination_31_to_90d,
    count(*) FILTER (WHERE transfer_lineage_status = 'SUCCESSOR_WITHIN_30D_DESTINATION_MISMATCH')::bigint AS successor_within_30d_destination_mismatch,
    count(*) FILTER (WHERE transfer_lineage_status = 'SUCCESSOR_31_TO_90D_DESTINATION_MISMATCH')::bigint AS successor_31_to_90d_destination_mismatch,
    count(*) FILTER (WHERE transfer_lineage_status LIKE '%DESTINATION_UNVERIFIABLE')::bigint AS successor_destination_unverifiable,
    count(*) FILTER (WHERE transfer_lineage_status = 'REPORTED_NO_SUCCESSOR_WITHIN_90D')::bigint AS reported_without_successor_90d,
    count(*) FILTER (WHERE transfer_lineage_status = 'MISSING_CLIENT_KEY')::bigint AS missing_client_key,
    round(
        count(*) FILTER (WHERE successor_lineage_observed)::numeric
        / nullif(count(*), 0),
        4
    ) AS any_successor_lineage_coverage_90d,
    round(
        count(*) FILTER (WHERE declared_destination_lineage_verified)::numeric
        / nullif(count(*) FILTER (WHERE declared_destination_available), 0),
        4
    ) AS declared_destination_verification_coverage_90d
FROM decision_intelligence.v_department_transfer_lineage_audit;

COMMENT ON VIEW decision_intelligence.v_department_transfer_lineage_audit IS
'Reported department-transfer outcomes audited against subsequent same-client separations within 90 days, with destination matching when depa_del_cambio is available. Post-outcome only; not a live feature.';

COMMENT ON VIEW decision_intelligence.v_department_transfer_lineage_health IS
'Coverage and quality counters for generic successor lineage and CRM-declared destination verification.';
