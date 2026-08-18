-- Point-in-time snapshot contract for future backtesting, drift analysis and
-- false-negative investigation. Snapshotting the full universe (not only scored
-- candidates) preserves exclusion decisions and prevents survivor bias.

create table if not exists decision_intelligence.candidate_universe_snapshot (
    decision_key text not null,
    snapshot_at timestamptz not null,
    entity_type text not null,
    entity_id text not null,
    codigo_proforma text,
    codigo_unidad text,
    codigo_proyecto text,
    asesor text,
    eligibility_status text not null,
    eligibility_rule text,
    feature_contract_version text,
    evidence_snapshot jsonb not null default '{}'::jsonb,
    recorded_at timestamptz not null default now(),
    primary key (decision_key, snapshot_at, entity_type, entity_id)
);

create index if not exists ix_candidate_universe_snapshot_entity
    on decision_intelligence.candidate_universe_snapshot (
        decision_key, entity_type, entity_id, snapshot_at desc
    );

create or replace function decision_intelligence.snapshot_separation_fall_risk_universe()
returns integer
language plpgsql
as $$
declare
    affected integer := 0;
begin
    insert into decision_intelligence.candidate_universe_snapshot (
        decision_key,
        snapshot_at,
        entity_type,
        entity_id,
        codigo_proforma,
        codigo_unidad,
        codigo_proyecto,
        asesor,
        eligibility_status,
        eligibility_rule,
        feature_contract_version,
        evidence_snapshot
    )
    select
        'separation_fall_risk',
        u.observed_at,
        'separation',
        u.separation_id,
        u.codigo_proforma,
        u.codigo_unidad,
        u.codigo_proyecto,
        u.asesor,
        u.eligibility_status,
        u.eligibility_rule,
        'separation-fall-risk-current-v0.5.0',
        jsonb_build_object(
            'fecha_separacion', u.fecha_separacion,
            'proforma_first_seen_at', u.proforma_first_seen_at,
            'proforma_age_days', u.proforma_age_days,
            'eligibility_window_months', u.eligibility_window_months,
            'estado_separacion_actual', u.estado_separacion_actual,
            'pago_ci_marker_raw', u.pago_ci_marker_raw,
            'pago_ci_marker_confirmado', u.pago_ci_marker_confirmado,
            'pago_ci_marker_desconocido', u.pago_ci_marker_desconocido,
            'fecha_pago_ci', u.fecha_pago_ci,
            'has_active_entrega_process', u.has_active_entrega_process,
            'active_entrega_process_count', u.active_entrega_process_count,
            'active_entrega_source_id', u.active_entrega_source_id,
            'monto_total_pagado', u.monto_total_pagado,
            'monto_pagado_de_cuota_inicial', u.monto_pagado_de_cuota_inicial,
            'monto_pagado_cuota_inicial', u.monto_pagado_cuota_inicial,
            'monto_pago_ci_positivo', u.monto_pago_ci_positivo,
            'monto_pago_ci_parse_error', u.monto_pago_ci_parse_error,
            'evidencia_pago_ci_confirmada', u.evidencia_pago_ci_confirmimada
        )
    from features.v_separation_fall_risk_candidate_universe u
    where u.observed_at is not null
    on conflict (decision_key, snapshot_at, entity_type, entity_id)
    do update set
        codigo_proforma = excluded.codigo_proforma,
        codigo_unidad = excluded.codigo_unidad,
        codigo_proyecto = excluded.codigo_proyecto,
        asesor = excluded.asesor,
        eligibility_status = excluded.eligibility_status,
        eligibility_rule = excluded.eligibility_rule,
        feature_contract_version = excluded.feature_contract_version,
        evidence_snapshot = excluded.evidence_snapshot,
        recorded_at = now();

    get diagnostics affected = row_count;
    return affected;
end;
$$;

create or replace view decision_intelligence.v_candidate_universe_snapshot_health as
select
    decision_key,
    snapshot_at,
    count(*) as universe_entities,
    count(*) filter (where eligibility_status = 'ELIGIBLE') as eligible_entities,
    count(*) filter (where eligibility_status like 'EXCLUDED_%') as excluded_entities,
    count(*) filter (where eligibility_status like 'BLOCKED_%') as blocked_entities,
    count(distinct entity_id) as distinct_entities,
    count(*) - count(distinct entity_id) as duplicate_entities
from decision_intelligence.candidate_universe_snapshot
group by decision_key, snapshot_at;

comment on table decision_intelligence.candidate_universe_snapshot is
'Point-in-time full decision universe, including excluded/blocked entities, for evaluation and audit.';
