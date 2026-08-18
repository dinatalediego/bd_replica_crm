-- Historical outcomes and post-outcome text evidence for separation_fall_risk.
--
-- IMPORTANT LEAKAGE RULE:
-- motivo_caida_segun_asesor, cambio_de_departamento and depa_del_cambio are
-- outcome/post-outcome evidence. They are useful to understand historical falls,
-- build reason taxonomies and audit labels, but MUST NOT enter the live/current
-- risk feature set unless a future point-in-time contract proves the value was
-- already known before decision_observed_at.
--
-- The supervised outcome of interest is FALL BEFORE CONVERSION. Confirmed
-- initial-payment evidence is therefore a successful-conversion outcome and has
-- precedence over a raw/legacy CAIDA state when both signals coexist.

create schema if not exists decision_intelligence;

create or replace view decision_intelligence.v_proforma_outcome_text_latest as
with latest_non_empty as (
    select distinct on (de.codigo::text, lower(de.nombre::text))
        de.codigo::text as codigo_proforma,
        lower(de.nombre::text) as nombre,
        nullif(btrim(de.valor::text), '') as valor,
        de.id as source_id,
        de.fecha_actualizacion as source_updated_at
    from raw_cygnus.datos_extras de
    where lower(coalesce(de.entidad::text, '')) = 'proforma'
      and lower(coalesce(de.nombre::text, '')) in (
          'motivo_caida_segun_asesor',
          'cambio_de_departamento',
          'depa_del_cambio'
      )
      and nullif(btrim(de.valor::text), '') is not null
    order by
        de.codigo::text,
        lower(de.nombre::text),
        de.fecha_actualizacion desc nulls last,
        de.id desc
)
select
    codigo_proforma,
    max(valor) filter (where nombre = 'motivo_caida_segun_asesor') as motivo_caida_segun_asesor,
    max(valor) filter (where nombre = 'cambio_de_departamento') as cambio_de_departamento,
    max(valor) filter (where nombre = 'depa_del_cambio') as depa_del_cambio,
    max(source_updated_at) filter (where nombre = 'motivo_caida_segun_asesor') as motivo_caida_updated_at,
    max(source_updated_at) filter (where nombre = 'cambio_de_departamento') as cambio_de_departamento_updated_at,
    max(source_updated_at) filter (where nombre = 'depa_del_cambio') as depa_del_cambio_updated_at
from latest_non_empty
group by codigo_proforma;

create or replace view decision_intelligence.v_separation_fall_outcome_history as
select
    'separacion:' || c.separacion_source_id::text as separation_id,
    c.codigo_proforma,
    c.codigo_unidad,
    coalesce(c.codigo_proyecto_ciclo, c.codigo_proyecto_unidad) as codigo_proyecto,
    c.documento_cliente,
    c.asesor,
    c.tipo_unidad_principal,
    c.fecha_separacion,
    c.primera_fecha_caida,
    c.ultima_fecha_caida,
    c.fecha_pago_ci,
    c.fecha_venta,
    c.metodo_fecha_venta,
    c.resultado_ciclo as resultado_ciclo_raw,
    c.pago_ci_marker_confirmado,
    c.monto_pago_ci_positivo,
    c.evidencia_pago_ci_confirmada,

    -- Conversion takes precedence because the business target is whether an
    -- opportunity falls BEFORE showing confirmed initial-payment interest.
    case
        when c.evidencia_pago_ci_confirmada or c.resultado_ciclo = 'VENTA'
            then 'CONVERTED'
        when c.resultado_ciclo = 'CAIDA'
            then 'FELL'
        when c.resultado_ciclo = 'ABIERTA'
            then 'CENSORED_OPEN'
        else 'UNKNOWN'
    end::text as outcome_class,

    case
        when c.evidencia_pago_ci_confirmada or c.resultado_ciclo = 'VENTA'
            then 0
        when c.resultado_ciclo = 'CAIDA'
            then 1
        else null::integer
    end as target_fall_before_conversion,

    case
        when c.evidencia_pago_ci_confirmada or c.resultado_ciclo = 'VENTA'
            then coalesce(c.fecha_pago_ci, c.fecha_venta)
        when c.resultado_ciclo = 'CAIDA'
            then c.primera_fecha_caida
        else null
    end as outcome_at,

    case
        when c.fecha_pago_ci is not null then 'DATED_INITIAL_PAYMENT'
        when c.pago_ci_marker_confirmado then 'INITIAL_PAYMENT_MARKER'
        when c.monto_pago_ci_positivo then 'POSITIVE_INITIAL_PAYMENT_AMOUNT'
        when c.resultado_ciclo = 'VENTA' then coalesce(c.metodo_fecha_venta, 'CORE_VENTA')
        else null
    end::text as conversion_evidence_mode,

    case
        when (c.evidencia_pago_ci_confirmada or c.resultado_ciclo = 'VENTA')
          and coalesce(c.fecha_pago_ci, c.fecha_venta) is null
            then false
        when c.resultado_ciclo = 'CAIDA' and c.primera_fecha_caida is null
            then false
        when c.resultado_ciclo in ('VENTA', 'CAIDA') or c.evidencia_pago_ci_confirmada
            then true
        else null::boolean
    end as outcome_has_temporal_precision,

    case
        when c.fecha_separacion is null then null::integer
        when c.evidencia_pago_ci_confirmada or c.resultado_ciclo = 'VENTA'
            then greatest(0, coalesce(c.fecha_pago_ci, c.fecha_venta)::date - c.fecha_separacion::date)::integer
        when c.resultado_ciclo = 'CAIDA' and c.primera_fecha_caida is not null
            then greatest(0, c.primera_fecha_caida::date - c.fecha_separacion::date)::integer
        else null::integer
    end as days_to_outcome,

    t.motivo_caida_segun_asesor,
    t.cambio_de_departamento,
    t.depa_del_cambio,
    t.motivo_caida_updated_at,
    t.cambio_de_departamento_updated_at,
    t.depa_del_cambio_updated_at,
    (nullif(btrim(t.motivo_caida_segun_asesor), '') is not null) as has_fall_reason_text,

    -- Explicit metadata to stop accidental feature leakage.
    'POST_OUTCOME_ONLY'::text as fall_reason_text_role,
    false::boolean as fall_reason_live_feature_eligible,
    c.analytics_refreshed_at
from core.fact_ciclo_comercial_unidad c
left join decision_intelligence.v_proforma_outcome_text_latest t
  on t.codigo_proforma = c.codigo_proforma
where c.separacion_source_id is not null;

-- One row per proforma for text mining. A proforma can contain apartment +
-- parking/deposit units; counting every unit would overweight the same written
-- reason. Prefer a residential lifecycle row when one exists.
create or replace view decision_intelligence.v_fall_reason_proforma_history as
with ranked as (
    select
        h.*,
        row_number() over (
            partition by h.codigo_proforma
            order by
                case when lower(coalesce(h.tipo_unidad_principal, '')) in (
                    'departamento flat', 'departamento duplex', 'departamento triplex'
                ) then 0 else 1 end,
                h.outcome_at desc nulls last,
                h.codigo_unidad
        ) as rn
    from decision_intelligence.v_separation_fall_outcome_history h
    where h.target_fall_before_conversion = 1
)
select
    codigo_proforma,
    codigo_proyecto,
    asesor,
    fecha_separacion,
    outcome_at as fecha_caida,
    days_to_outcome as days_to_fall,
    motivo_caida_segun_asesor,
    cambio_de_departamento,
    depa_del_cambio,
    motivo_caida_updated_at,
    has_fall_reason_text,
    fall_reason_text_role
from ranked
where rn = 1;

create or replace view decision_intelligence.v_separation_fall_outcome_health as
select
    count(*)::bigint as lifecycle_rows,
    count(*) filter (where target_fall_before_conversion is not null)::bigint as labeled_rows,
    count(*) filter (where target_fall_before_conversion = 1)::bigint as fall_rows,
    count(*) filter (where target_fall_before_conversion = 0)::bigint as conversion_rows,
    count(*) filter (where outcome_class = 'CENSORED_OPEN')::bigint as censored_open_rows,
    count(*) filter (
        where target_fall_before_conversion is not null
          and outcome_has_temporal_precision = false
    )::bigint as labeled_without_temporal_precision,
    count(*) filter (
        where target_fall_before_conversion = 1
          and has_fall_reason_text
    )::bigint as falls_with_reason_text,
    round(
        count(*) filter (
            where target_fall_before_conversion = 1
              and has_fall_reason_text
        )::numeric
        / nullif(count(*) filter (where target_fall_before_conversion = 1), 0),
        4
    ) as fall_reason_text_coverage,
    count(*) filter (
        where resultado_ciclo_raw = 'CAIDA'
          and target_fall_before_conversion = 0
    )::bigint as raw_fall_reclassified_as_conversion_due_payment_evidence
from decision_intelligence.v_separation_fall_outcome_history;

comment on view decision_intelligence.v_separation_fall_outcome_history is
'Historical labels for fall-before-conversion. Initial-payment evidence is conversion; fall-reason text is post-outcome only and forbidden as a live risk feature.';

comment on view decision_intelligence.v_fall_reason_proforma_history is
'One-row-per-proforma historical fall corpus for NLP/taxonomy analysis without unit-level duplication.';
