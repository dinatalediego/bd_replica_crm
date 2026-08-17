-- Operational contract for the first real end-to-end decision.
-- Prerequisite: decision_engine/sql/00_decision_control.sql

create unique index if not exists ux_recommendation_idempotent
    on decision_intelligence.recommendation (
        decision_key, entity_type, entity_id, observed_at, policy_version
    );

-- The Decision Engine deliberately consumes a trusted feature contract.
-- Expected relation: features.separation_fall_risk_current
-- Required columns:
-- separation_id text, observed_at timestamptz,
-- days_since_separation integer, days_since_last_interaction integer,
-- interaction_count_14d integer, has_pending_admin_block boolean,
-- quality_status text, quality_reasons text[].
--
-- This view is intentionally NOT created from raw_cygnus here. Reconstructing
-- a commercial cycle from a single RAW row would violate DATA_CONTRACT_V0.md.

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
    *,
    case action
        when 'urgent_follow_up' then 1
        when 'follow_up' then 2
        when 'monitor' then 3
        else 99
    end as action_priority
from decision_intelligence.v_separation_fall_risk_latest
where status = 'ACTIVE';
