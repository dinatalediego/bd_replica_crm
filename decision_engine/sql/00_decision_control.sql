create schema if not exists decision_intelligence;

create table if not exists decision_intelligence.recommendation (
    recommendation_id uuid primary key,
    decision_key text not null,
    entity_type text not null,
    entity_id text not null,
    observed_at timestamptz not null,
    generated_at timestamptz not null default now(),
    action text not null,
    score numeric,
    confidence numeric,
    expected_value numeric,
    policy_version text not null,
    explanation text,
    quality_status text not null default 'OK',
    status text not null default 'ACTIVE',
    expires_at timestamptz,
    feature_snapshot jsonb not null default '{}'::jsonb,
    evidence jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ix_recommendation_lookup
    on decision_intelligence.recommendation (decision_key, entity_type, entity_id, observed_at desc);

create table if not exists decision_intelligence.recommendation_feedback (
    feedback_id bigserial primary key,
    recommendation_id uuid not null references decision_intelligence.recommendation(recommendation_id),
    actor text,
    disposition text not null check (disposition in ('SHOWN','ACCEPTED','MODIFIED','REJECTED','EXPIRED')),
    chosen_action text,
    reason text,
    recorded_at timestamptz not null default now()
);

create table if not exists decision_intelligence.recommendation_outcome (
    recommendation_id uuid primary key references decision_intelligence.recommendation(recommendation_id),
    outcome_name text not null,
    outcome_value jsonb,
    economic_value numeric,
    observed_at timestamptz not null,
    recorded_at timestamptz not null default now()
);

create table if not exists decision_intelligence.quality_gate_event (
    gate_event_id bigserial primary key,
    decision_key text not null,
    entity_type text not null,
    entity_id text,
    gate_name text not null,
    severity text not null check (severity in ('WARN','BLOCK')),
    reason text not null,
    observed_at timestamptz not null,
    resolved_at timestamptz
);

comment on schema decision_intelligence is
'Decision outputs, human feedback, outcomes and quality gates. Trusted source metrics remain in analytics.';
