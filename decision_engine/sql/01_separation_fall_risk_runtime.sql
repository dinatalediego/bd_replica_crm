-- Operational contract for the first real end-to-end decision.
-- Prerequisite: decision_engine/sql/00_decision_control.sql

create unique index if not exists ux_recommendation_idempotent
    on decision_intelligence.recommendation (
        decision_key, entity_type, entity_id, observed_at, policy_version
    );

-- The Decision Engine consumes the trusted contract published by
-- decision_engine/sql/02_separation_fall_risk_features.sql.

create or replace view decision_intelligence.v_separation_fall_risk_latest as
select
    recommendation_id,
    entity_id as separation_id,
    observed_at,
    generated_at,
    action,
    score,
    quality_status,
    status,
    policy_version,
    explanation,
    feature_snapshot,
    evidence
from (
    select
        r.*,
        row_number() over (
            partition by decision_key, entity_type, entity_id
            order by observed_at desc, generated_at desc
        ) as rn
    from decision_intelligence.recommendation r
    where decision_key = 'separation_fall_risk'
      and entity_type = 'separation'
) ranked
where rn = 1;

create or replace view decision_intelligence.v_separation_fall_risk_worklist as
select
    recommendation_id,
    separation_id,
    observed_at,
    generated_at,
    action,
    score,
    quality_status,
    status,
    policy_version,
    explanation,

    feature_snapshot ->> 'codigo_proforma' as codigo_proforma,
    feature_snapshot ->> 'codigo_unidad' as codigo_unidad,
    feature_snapshot ->> 'codigo_proyecto' as codigo_proyecto,
    feature_snapshot ->> 'documento_cliente' as documento_cliente,
    feature_snapshot ->> 'asesor' as asesor,
    (feature_snapshot ->> 'fecha_separacion')::date as fecha_separacion,
    (feature_snapshot ->> 'days_since_separation')::integer as days_since_separation,
    (feature_snapshot ->> 'days_since_last_interaction')::integer as days_since_last_interaction,
    (feature_snapshot ->> 'interaction_count_14d')::integer as interaction_count_14d,
    nullif(feature_snapshot ->> 'has_pending_admin_block', '')::boolean as has_pending_admin_block,
    feature_snapshot ->> 'interaction_signal_mode' as interaction_signal_mode,
    feature_snapshot ->> 'admin_signal_mode' as admin_signal_mode,
    feature_snapshot ->> 'feature_contract_version' as feature_contract_version,

    feature_snapshot,
    evidence,
    case action
        when 'urgent_follow_up' then 1
        when 'follow_up' then 2
        when 'monitor' then 3
        else 99
    end as action_priority
from decision_intelligence.v_separation_fall_risk_latest
where status = 'ACTIVE';
