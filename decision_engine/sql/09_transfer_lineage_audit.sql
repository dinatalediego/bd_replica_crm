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

create or replace view decision_intelligence.v_department_transfer_lineage_audit as
with transfer_base as (
    select
        t.*,
        a.cambio_de_departamento,
        a.depa_del_cambio,
        a.motivo_caida_segun_asesor,
        regexp_replace(
            translate(lower(coalesce(a.depa_del_cambio, '')), 'áéíóúüñ', 'aeiouun'),
            '[^a-z0-9]+', '', 'g'
        ) as declared_destination_norm
    from decision_intelligence.v_separation_fall_training_outcome t
    left join decision_intelligence.v_fall_reason_analysis_corpus a
      on a.codigo_proforma = t.codigo_proforma
    where t.training_outcome_class = 'TRANSFER_UNIT'
)
select
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
    true::boolean as transfer_reported_in_crm,
    s.successor_codigo_proforma,
    s.successor_codigo_unidad,
    s.successor_codigo_proyecto,
    s.successor_nombre_unidad,
    s.successor_nombre_proyecto,
    s.successor_separacion_at,
    case
        when s.successor_separacion_at is not null
         and t.primera_fecha_caida is not null
        then (s.successor_separacion_at::date - t.primera_fecha_caida::date)::integer
        else null::integer
    end as days_to_successor_separation,
    nullif(t.declared_destination_norm, '') is not null as declared_destination_available,
    coalesce(s.destination_match_score, 0)::integer as destination_match_score,
    case
        when nullif(t.declared_destination_norm, '') is null
            then 'NO_DECLARED_DESTINATION'
        when s.successor_separacion_at is null
            then 'NO_SUCCESSOR_TO_COMPARE'
        when s.destination_match_score >= 3
            then 'DECLARED_UNIT_MATCH'
        when s.destination_match_score = 2
            then 'PROJECT_AND_UNIT_NUMBER_MATCH'
        when s.destination_match_score = 1
            then 'UNIT_NUMBER_ONLY_MATCH'
        else 'DECLARED_DESTINATION_MISMATCH'
    end::text as destination_match_status,
    case
        when t.documento_cliente is null then 'MISSING_CLIENT_KEY'
        when s.successor_separacion_at is null then 'REPORTED_NO_SUCCESSOR_WITHIN_90D'
        when nullif(t.declared_destination_norm, '') is null
         and s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            then 'SUCCESSOR_WITHIN_30D_DESTINATION_UNVERIFIABLE'
        when nullif(t.declared_destination_norm, '') is null
            then 'SUCCESSOR_31_TO_90D_DESTINATION_UNVERIFIABLE'
        when s.destination_match_score > 0
         and s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            then 'VERIFIED_DESTINATION_WITHIN_30D'
        when s.destination_match_score > 0
            then 'VERIFIED_DESTINATION_31_TO_90D'
        when s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            then 'SUCCESSOR_WITHIN_30D_DESTINATION_MISMATCH'
        else 'SUCCESSOR_31_TO_90D_DESTINATION_MISMATCH'
    end::text as transfer_lineage_status,
    (s.successor_separacion_at is not null) as successor_lineage_observed,
    (
        s.successor_separacion_at is not null
        and s.destination_match_score > 0
        and nullif(t.declared_destination_norm, '') is not null
    ) as declared_destination_lineage_verified,
    'POST_OUTCOME_AUDIT_ONLY'::text as lineage_evidence_role,
    false::boolean as lineage_live_feature_eligible
from transfer_base t
left join lateral (
    select
        z.successor_codigo_proforma,
        z.successor_codigo_unidad,
        z.successor_codigo_proyecto,
        z.successor_nombre_unidad,
        z.successor_nombre_proyecto,
        z.successor_separacion_at,
        z.destination_match_score
    from (
        select
            p.codigo_proforma::text as successor_codigo_proforma,
            p.codigo_unidad::text as successor_codigo_unidad,
            p.codigo_proyecto::text as successor_codigo_proyecto,
            u.nombre_unidad::text as successor_nombre_unidad,
            dp.nombre_proyecto::text as successor_nombre_proyecto,
            p.fecha_inicio as successor_separacion_at,
            p.id as successor_source_id,
            case
                -- Strongest: declared text contains the canonical unit name.
                when nullif(t.declared_destination_norm, '') is not null
                 and nullif(
                    regexp_replace(
                        translate(lower(coalesce(u.nombre_unidad::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                    ), ''
                 ) is not null
                 and t.declared_destination_norm like '%' || regexp_replace(
                        translate(lower(coalesce(u.nombre_unidad::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                     ) || '%'
                    then 3

                -- Strong: project name plus numeric portion of unit agree.
                when nullif(t.declared_destination_norm, '') is not null
                 and nullif(
                    regexp_replace(
                        translate(lower(coalesce(dp.nombre_proyecto::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                    ), ''
                 ) is not null
                 and t.declared_destination_norm like '%' || regexp_replace(
                        translate(lower(coalesce(dp.nombre_proyecto::text, '')), 'áéíóúüñ', 'aeiouun'),
                        '[^a-z0-9]+', '', 'g'
                     ) || '%'
                 and length(regexp_replace(coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g')) >= 2
                 and t.declared_destination_norm like '%' || regexp_replace(
                        coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g'
                     ) || '%'
                    then 2

                -- Weak but useful for abbreviated CRM destinations such as E-B24.
                when nullif(t.declared_destination_norm, '') is not null
                 and length(regexp_replace(coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g')) >= 2
                 and t.declared_destination_norm like '%' || regexp_replace(
                        coalesce(u.nombre_unidad::text, ''), '[^0-9]+', '', 'g'
                     ) || '%'
                    then 1
                else 0
            end::integer as destination_match_score
        from raw_cygnus.procesos p
        left join core.dim_unidad u
          on u.codigo_unidad = p.codigo_unidad::text
        left join core.dim_proyecto dp
          on dp.codigo_proyecto = p.codigo_proyecto::text
        where lower(coalesce(p.nombre::text, '')) = 'separacion'
          and p.documento_cliente::text = t.documento_cliente::text
          and p.codigo_proforma is not null
          and p.codigo_proforma::text <> t.codigo_proforma
          and p.fecha_inicio is not null
          and t.primera_fecha_caida is not null
          and p.fecha_inicio::date >= t.primera_fecha_caida::date
          and p.fecha_inicio::date <= t.primera_fecha_caida::date + 90
          and coalesce(p.nombre_flujo::text, '') <> 'Desistimiento de visita'
    ) z
    order by
        -- When CRM names a destination, prefer a matching successor over an
        -- unrelated earlier same-client separation. Without destination text,
        -- preserve chronological-first semantics.
        case when nullif(t.declared_destination_norm, '') is not null
             then z.destination_match_score else 0 end desc,
        z.successor_separacion_at,
        z.successor_source_id
    limit 1
) s on true;

create or replace view decision_intelligence.v_department_transfer_lineage_health as
select
    count(*)::bigint as reported_transfer_rows,
    count(*) filter (where successor_lineage_observed)::bigint as transfers_with_any_successor_90d,
    count(*) filter (where declared_destination_lineage_verified)::bigint as transfers_with_verified_destination_90d,
    count(*) filter (where transfer_lineage_status = 'VERIFIED_DESTINATION_WITHIN_30D')::bigint as verified_destination_within_30d,
    count(*) filter (where transfer_lineage_status = 'VERIFIED_DESTINATION_31_TO_90D')::bigint as verified_destination_31_to_90d,
    count(*) filter (where transfer_lineage_status = 'SUCCESSOR_WITHIN_30D_DESTINATION_MISMATCH')::bigint as successor_within_30d_destination_mismatch,
    count(*) filter (where transfer_lineage_status = 'SUCCESSOR_31_TO_90D_DESTINATION_MISMATCH')::bigint as successor_31_to_90d_destination_mismatch,
    count(*) filter (where transfer_lineage_status like '%DESTINATION_UNVERIFIABLE')::bigint as successor_destination_unverifiable,
    count(*) filter (where transfer_lineage_status = 'REPORTED_NO_SUCCESSOR_WITHIN_90D')::bigint as reported_without_successor_90d,
    count(*) filter (where transfer_lineage_status = 'MISSING_CLIENT_KEY')::bigint as missing_client_key,
    round(
        count(*) filter (where successor_lineage_observed)::numeric
        / nullif(count(*), 0),
        4
    ) as any_successor_lineage_coverage_90d,
    round(
        count(*) filter (where declared_destination_lineage_verified)::numeric
        / nullif(count(*) filter (where declared_destination_available), 0),
        4
    ) as declared_destination_verification_coverage_90d
from decision_intelligence.v_department_transfer_lineage_audit;

comment on view decision_intelligence.v_department_transfer_lineage_audit is
'Reported department-transfer outcomes audited against subsequent same-client separations within 90 days, with destination matching when depa_del_cambio is available. Post-outcome only; not a live feature.';

comment on view decision_intelligence.v_department_transfer_lineage_health is
'Coverage and quality counters for generic successor lineage and CRM-declared destination verification.';
