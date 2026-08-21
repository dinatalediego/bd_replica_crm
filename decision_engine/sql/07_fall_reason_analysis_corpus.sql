-- Governed analysis corpus for historical fall reasons.
--
-- This layer deliberately broadens analysis beyond free text alone. The CRM
-- sometimes records a structured department-change signal even when
-- motivo_caida_segun_asesor is blank. Those rows are informative historical
-- outcomes and should be analysed, but none of these post-outcome fields is
-- eligible for live scoring.

create or replace view decision_intelligence.v_fall_reason_analysis_corpus as
select
    h.*,
    (nullif(btrim(h.motivo_caida_segun_asesor), '') is not null) as has_motivo_text,
    (
        nullif(btrim(h.depa_del_cambio), '') is not null
        or lower(coalesce(h.cambio_de_departamento, '')) like '%cambi%'
        or lower(coalesce(h.cambio_de_departamento, '')) like '%otro departamento%'
    ) as has_confirmed_department_change,
    (
        nullif(btrim(h.motivo_caida_segun_asesor), '') is not null
        or nullif(btrim(h.cambio_de_departamento), '') is not null
        or nullif(btrim(h.depa_del_cambio), '') is not null
    ) as has_any_reason_evidence,
    case
        when nullif(btrim(h.motivo_caida_segun_asesor), '') is not null
         and (
            nullif(btrim(h.depa_del_cambio), '') is not null
            or lower(coalesce(h.cambio_de_departamento, '')) like '%cambi%'
            or lower(coalesce(h.cambio_de_departamento, '')) like '%otro departamento%'
         ) then 'TEXT_PLUS_STRUCTURED_CHANGE'
        when nullif(btrim(h.motivo_caida_segun_asesor), '') is not null
            then 'TEXT_ONLY'
        when (
            nullif(btrim(h.depa_del_cambio), '') is not null
            or lower(coalesce(h.cambio_de_departamento, '')) like '%cambi%'
            or lower(coalesce(h.cambio_de_departamento, '')) like '%otro departamento%'
        ) then 'STRUCTURED_CHANGE_ONLY'
        when nullif(btrim(h.cambio_de_departamento), '') is not null
            then 'STRUCTURED_OTHER_ONLY'
        else 'NO_REASON_EVIDENCE'
    end::text as reason_evidence_mode,
    'POST_OUTCOME_ONLY'::text as reason_evidence_role,
    false::boolean as reason_evidence_live_feature_eligible
from decision_intelligence.v_fall_reason_proforma_history h;

create or replace view decision_intelligence.v_fall_reason_analysis_health as
select
    count(*)::bigint as fall_proformas,
    count(*) filter (where has_motivo_text)::bigint as with_free_text,
    count(*) filter (where has_confirmed_department_change)::bigint as with_confirmed_department_change,
    count(*) filter (where has_any_reason_evidence)::bigint as with_any_reason_evidence,
    count(*) filter (where reason_evidence_mode = 'TEXT_PLUS_STRUCTURED_CHANGE')::bigint as text_plus_structured_change,
    count(*) filter (where reason_evidence_mode = 'TEXT_ONLY')::bigint as text_only,
    count(*) filter (where reason_evidence_mode = 'STRUCTURED_CHANGE_ONLY')::bigint as structured_change_only,
    count(*) filter (where reason_evidence_mode = 'STRUCTURED_OTHER_ONLY')::bigint as structured_other_only,
    count(*) filter (where reason_evidence_mode = 'NO_REASON_EVIDENCE')::bigint as without_reason_evidence,
    round(
        count(*) filter (where has_motivo_text)::numeric / nullif(count(*), 0),
        4
    ) as free_text_coverage,
    round(
        count(*) filter (where has_any_reason_evidence)::numeric / nullif(count(*), 0),
        4
    ) as any_reason_evidence_coverage
from decision_intelligence.v_fall_reason_analysis_corpus;

comment on view decision_intelligence.v_fall_reason_analysis_corpus is
'Historical fall-reason corpus combining free-text and structured change evidence. Post-outcome only; forbidden as live risk features.';
