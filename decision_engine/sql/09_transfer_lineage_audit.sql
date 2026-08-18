-- Audit reported department transfers against observable successor separations.
--
-- Purpose:
-- * distinguish a CRM-reported transfer from a lineage-verified continuation;
-- * never use transfer/post-outcome evidence as a live feature;
-- * keep reported transfers excluded from binary training conservatively until
--   successor lineage is certified;
-- * surface evidence quality before any model training.

create or replace view decision_intelligence.v_department_transfer_lineage_audit as
select
    t.separation_id,
    t.codigo_proforma,
    t.codigo_unidad,
    t.codigo_proyecto,
    t.documento_cliente,
    t.asesor,
    t.fecha_separacion,
    t.primera_fecha_caida,
    a.cambio_de_departamento,
    a.depa_del_cambio,
    a.motivo_caida_segun_asesor,
    true::boolean as transfer_reported_in_crm,
    s.successor_codigo_proforma,
    s.successor_codigo_unidad,
    s.successor_codigo_proyecto,
    s.successor_separacion_at,
    case
        when s.successor_separacion_at is not null
         and t.primera_fecha_caida is not null
        then (s.successor_separacion_at::date - t.primera_fecha_caida::date)::integer
        else null::integer
    end as days_to_successor_separation,
    case
        when t.documento_cliente is null then 'MISSING_CLIENT_KEY'
        when s.successor_separacion_at is null then 'REPORTED_NO_SUCCESSOR_WITHIN_90D'
        when s.successor_separacion_at::date <= t.primera_fecha_caida::date + 30
            then 'SUCCESSOR_WITHIN_30D'
        else 'SUCCESSOR_31_TO_90D'
    end::text as transfer_lineage_status,
    (s.successor_separacion_at is not null) as successor_lineage_observed,
    'POST_OUTCOME_AUDIT_ONLY'::text as lineage_evidence_role,
    false::boolean as lineage_live_feature_eligible
from decision_intelligence.v_separation_fall_training_outcome t
left join decision_intelligence.v_fall_reason_analysis_corpus a
  on a.codigo_proforma = t.codigo_proforma
left join lateral (
    select
        p.codigo_proforma::text as successor_codigo_proforma,
        p.codigo_unidad::text as successor_codigo_unidad,
        p.codigo_proyecto::text as successor_codigo_proyecto,
        p.fecha_inicio as successor_separacion_at
    from raw_cygnus.procesos p
    where lower(coalesce(p.nombre::text, '')) = 'separacion'
      and p.documento_cliente::text = t.documento_cliente::text
      and p.codigo_proforma is not null
      and p.codigo_proforma::text <> t.codigo_proforma
      and p.fecha_inicio is not null
      and t.primera_fecha_caida is not null
      and p.fecha_inicio::date >= t.primera_fecha_caida::date
      and p.fecha_inicio::date <= t.primera_fecha_caida::date + 90
      and coalesce(p.nombre_flujo::text, '') <> 'Desistimiento de visita'
    order by p.fecha_inicio, p.id
    limit 1
) s on true
where t.training_outcome_class = 'TRANSFER_UNIT';

create or replace view decision_intelligence.v_department_transfer_lineage_health as
select
    count(*)::bigint as reported_transfer_rows,
    count(*) filter (where successor_lineage_observed)::bigint as transfers_with_successor_90d,
    count(*) filter (where transfer_lineage_status = 'SUCCESSOR_WITHIN_30D')::bigint as successor_within_30d,
    count(*) filter (where transfer_lineage_status = 'SUCCESSOR_31_TO_90D')::bigint as successor_31_to_90d,
    count(*) filter (where transfer_lineage_status = 'REPORTED_NO_SUCCESSOR_WITHIN_90D')::bigint as reported_without_successor_90d,
    count(*) filter (where transfer_lineage_status = 'MISSING_CLIENT_KEY')::bigint as missing_client_key,
    round(
        count(*) filter (where successor_lineage_observed)::numeric
        / nullif(count(*), 0),
        4
    ) as successor_lineage_coverage_90d
from decision_intelligence.v_department_transfer_lineage_audit;

comment on view decision_intelligence.v_department_transfer_lineage_audit is
'Reported department-transfer outcomes audited against a subsequent separation for the same client within 90 days. Post-outcome only; not a live feature.';

comment on view decision_intelligence.v_department_transfer_lineage_health is
'Coverage and quality counters for transfer successor-lineage evidence.';
