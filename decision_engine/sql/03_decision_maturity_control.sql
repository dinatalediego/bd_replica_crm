-- Corporate-grade PolicyOps / DecisionOps control plane.
-- Additive: does not change recommendation semantics.

create schema if not exists decision_intelligence;

create table if not exists decision_intelligence.policy_registry (
    decision_key text not null,
    policy_version text not null,
    policy_type text not null check (policy_type in ('RULE','MODEL','HYBRID')),
    lifecycle_status text not null check (lifecycle_status in ('DRAFT','SHADOW','ACTIVE','PAUSED','RETIRED')),
    owner_business text not null,
    owner_technical text not null,
    feature_contract_version text,
    artifact_ref text,
    artifact_sha256 text,
    parameters jsonb not null default '{}'::jsonb,
    promotion_criteria jsonb not null default '{}'::jsonb,
    approved_by_business text,
    approved_by_technical text,
    approved_at timestamptz,
    effective_from timestamptz,
    retired_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (decision_key, policy_version)
);

create table if not exists decision_intelligence.decision_run (
    run_id uuid primary key,
    decision_key text not null,
    policy_version text not null,
    run_mode text not null check (run_mode in ('DRY_RUN','SHADOW','LIVE','BACKTEST')),
    observed_at timestamptz,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    run_status text not null check (run_status in ('RUNNING','SUCCESS','BLOCKED','FAILED')),
    candidate_count integer,
    recommendation_count integer,
    blocked_count integer,
    quality_snapshot jsonb not null default '{}'::jsonb,
    action_distribution jsonb not null default '{}'::jsonb,
    source_snapshot jsonb not null default '{}'::jsonb,
    git_sha text,
    error_message text,
    created_at timestamptz not null default now()
);

create index if not exists ix_decision_run_lookup
    on decision_intelligence.decision_run (decision_key, started_at desc);

create table if not exists decision_intelligence.experiment_registry (
    experiment_key text primary key,
    decision_key text not null,
    hypothesis text not null,
    unit_of_randomization text not null,
    primary_metric text not null,
    guardrail_metrics jsonb not null default '[]'::jsonb,
    treatment_policy_version text,
    control_policy_version text,
    status text not null check (status in ('DRAFT','RUNNING','PAUSED','COMPLETED','CANCELLED')),
    planned_start_at timestamptz,
    planned_end_at timestamptz,
    started_at timestamptz,
    ended_at timestamptz,
    owner text not null,
    pre_analysis_plan text,
    created_at timestamptz not null default now()
);

create table if not exists decision_intelligence.experiment_assignment (
    experiment_key text not null references decision_intelligence.experiment_registry(experiment_key),
    entity_type text not null,
    entity_id text not null,
    variant text not null,
    assigned_at timestamptz not null default now(),
    assignment_context jsonb not null default '{}'::jsonb,
    primary key (experiment_key, entity_type, entity_id)
);

create table if not exists decision_intelligence.production_incident (
    incident_id bigserial primary key,
    decision_key text,
    severity text not null check (severity in ('SEV1','SEV2','SEV3','SEV4')),
    category text not null check (category in ('DATA','QUALITY','MODEL','POLICY','PIPELINE','SECURITY','BUSINESS')),
    title text not null,
    description text,
    detected_at timestamptz not null default now(),
    resolved_at timestamptz,
    owner text,
    root_cause text,
    remediation text,
    status text not null default 'OPEN' check (status in ('OPEN','MITIGATED','RESOLVED'))
);

-- Coverage and realized-value view. It is intentionally generic so Power BI can
-- consume the same contract when more decision products are added.
create or replace view decision_intelligence.v_decision_value_scorecard as
with feedback as (
    select
        recommendation_id,
        bool_or(disposition in ('SHOWN','ACCEPTED','MODIFIED','REJECTED')) as reviewed,
        bool_or(disposition = 'ACCEPTED') as accepted,
        bool_or(disposition = 'MODIFIED') as modified,
        bool_or(disposition = 'REJECTED') as rejected
    from decision_intelligence.recommendation_feedback
    group by recommendation_id
), outcomes as (
    select
        recommendation_id,
        true as has_outcome,
        economic_value
    from decision_intelligence.recommendation_outcome
)
select
    r.decision_key,
    r.policy_version,
    date_trunc('month', r.generated_at) as period_month,
    count(*) as recommendations,
    count(*) filter (where r.status = 'ACTIVE') as active_recommendations,
    count(*) filter (where coalesce(f.reviewed, false)) as reviewed_recommendations,
    count(*) filter (where coalesce(f.accepted, false)) as accepted_recommendations,
    count(*) filter (where coalesce(f.modified, false)) as modified_recommendations,
    count(*) filter (where coalesce(f.rejected, false)) as rejected_recommendations,
    count(*) filter (where coalesce(o.has_outcome, false)) as recommendations_with_outcome,
    round(
        count(*) filter (where coalesce(o.has_outcome, false))::numeric
        / nullif(count(*), 0),
        4
    ) as outcome_coverage,
    round(
        count(*) filter (where coalesce(f.accepted, false))::numeric
        / nullif(count(*) filter (where coalesce(f.reviewed, false)), 0),
        4
    ) as acceptance_rate,
    sum(o.economic_value) as realized_economic_value
from decision_intelligence.recommendation r
left join feedback f using (recommendation_id)
left join outcomes o using (recommendation_id)
group by
    r.decision_key,
    r.policy_version,
    date_trunc('month', r.generated_at);

create or replace view decision_intelligence.v_policy_operational_health as
select
    p.decision_key,
    p.policy_version,
    p.policy_type,
    p.lifecycle_status,
    p.owner_business,
    p.owner_technical,
    p.feature_contract_version,
    p.approved_at,
    p.effective_from,
    max(r.started_at) as last_run_at,
    max(r.finished_at) filter (where r.run_status = 'SUCCESS') as last_success_at,
    count(*) filter (where r.started_at >= now() - interval '7 days') as runs_7d,
    count(*) filter (where r.started_at >= now() - interval '7 days' and r.run_status = 'FAILED') as failed_runs_7d,
    count(*) filter (where r.started_at >= now() - interval '7 days' and r.run_status = 'BLOCKED') as blocked_runs_7d
from decision_intelligence.policy_registry p
left join decision_intelligence.decision_run r
  on r.decision_key = p.decision_key
 and r.policy_version = p.policy_version
group by
    p.decision_key,
    p.policy_version,
    p.policy_type,
    p.lifecycle_status,
    p.owner_business,
    p.owner_technical,
    p.feature_contract_version,
    p.approved_at,
    p.effective_from;

comment on table decision_intelligence.policy_registry is
'Governed registry for rules/models/policies and their promotion lifecycle.';

comment on table decision_intelligence.decision_run is
'Run-level audit trail for dry-run, shadow, live and backtest executions.';

comment on table decision_intelligence.experiment_registry is
'Pre-registered experiments for causal evaluation of decision policies.';
