-- Register the first policy as SHADOW by default.
-- LIVE promotion must be an explicit governance action after evidence is collected.

insert into decision_intelligence.policy_registry (
    decision_key,
    policy_version,
    policy_type,
    lifecycle_status,
    owner_business,
    owner_technical,
    feature_contract_version,
    artifact_ref,
    parameters,
    promotion_criteria
)
values (
    'separation_fall_risk',
    'separation-fall-risk-baseline-v0.1.0',
    'RULE',
    'SHADOW',
    'commercial',
    'analytics',
    'separation_fall_risk_feature_contract',
    'decision_engine/src/cygnus_decision_engine/rules.py',
    jsonb_build_object(
        'days_since_separation_urgent', 21,
        'days_since_last_interaction_urgent', 7,
        'interaction_count_14d_zero_signal', true,
        'human_in_the_loop', true
    ),
    jsonb_build_object(
        'minimum_shadow_days', 14,
        'minimum_reviewed_recommendations', 30,
        'minimum_outcome_coverage', 0.80,
        'require_replication_parity', true,
        'require_baseline_comparison', true,
        'require_business_owner_approval', true,
        'require_technical_owner_approval', true
    )
)
on conflict (decision_key, policy_version) do nothing;
