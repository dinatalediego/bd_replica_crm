-- Medallio Pocket PROD: isolated sanitized Supabase schema.
-- This project is intentionally NOT a replica of medallio_dw.
-- Only aggregated/mobile-safe tables belong here.

begin;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists public.pocket_access (
    user_id uuid primary key references auth.users(id) on delete cascade,
    active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.pocket_project_month (
    project_ref text not null check (project_ref ~ '^[0-9a-f]{64}$'),
    project_name text not null,
    period_month date not null,
    source_cutoff date not null,
    is_partial boolean not null,
    stock_open bigint not null check (stock_open >= 0),
    gross_separations bigint not null check (gross_separations >= 0),
    falls bigint not null check (falls >= 0),
    net_separations bigint not null,
    sales_minutas bigint not null check (sales_minutas >= 0),
    stock_close bigint not null check (stock_close >= 0),
    gross_absorption numeric,
    net_absorption numeric,
    net_absorption_6m numeric,
    current_stock bigint,
    stock_coverage numeric,
    current_state_reconciled boolean,
    quality_status text not null,
    synced_at timestamptz not null default now(),
    primary key (project_ref, period_month)
);

create table if not exists public.pocket_project_summary (
    project_ref text primary key check (project_ref ~ '^[0-9a-f]{64}$'),
    project_name text not null,
    stage text not null default 'COMMERCIAL OBSERVED',
    stock bigint not null default 0 check (stock >= 0),
    sales_month bigint not null default 0 check (sales_month >= 0),
    absorption numeric not null default 0,
    amount_to_sell numeric not null default 0,
    months_to_zero numeric,
    price_m2 numeric,
    health_score integer not null default 0 check (health_score between 0 and 100),
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_forecast (
    project_ref text primary key check (project_ref ~ '^[0-9a-f]{64}$'),
    project_name text not null,
    model_version text not null,
    mae numeric,
    coverage numeric,
    trained_at timestamptz,
    points jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_pricing (
    project_ref text primary key check (project_ref ~ '^[0-9a-f]{64}$'),
    project_name text not null,
    list_price numeric,
    effective_price numeric,
    discount_pct numeric,
    price_m2 numeric,
    benchmark_m2 numeric,
    elasticity numeric,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_model_health (
    id text primary key,
    name text not null,
    purpose text not null,
    state text not null check (state in ('HEALTHY','WATCH','DEGRADED','NOT READY')),
    role text not null,
    version text not null,
    metric text not null,
    drift numeric,
    freshness text not null,
    readiness integer not null check (readiness between 0 and 100),
    confidence numeric,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_decision_summary_v2 (
    id text primary key,
    domain text not null,
    decision text not null,
    action text,
    outcome text,
    economic_value numeric,
    confidence numeric,
    risk text not null,
    status text not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_alerts (
    id text primary key,
    type text not null,
    severity text not null,
    project text,
    explanation text not null,
    recommendation text not null,
    evidence text,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_market_project (
    market_project_key text primary key,
    project_name text,
    available_units numeric,
    avg_price numeric,
    avg_price_m2 numeric,
    typology_count integer,
    updated_at timestamptz not null default now()
);

create table if not exists public.pocket_system_health_v2 (
    singleton boolean primary key default true check (singleton),
    last_success_at timestamptz,
    loads_24h bigint not null default 0,
    failed_24h bigint not null default 0,
    rows_24h bigint not null default 0,
    quality_score integer not null default 0 check (quality_score between 0 and 100),
    pii_found integer not null default 0 check (pii_found >= 0),
    updated_at timestamptz not null default now()
);

create table if not exists private.pocket_sync_runs (
    sync_run_id bigint generated always as identity primary key,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null default 'running',
    source_rows bigint,
    target_rows bigint,
    source_cutoff date,
    error_message text
);

-- Deny anonymous access explicitly.
do $$
declare t text;
begin
  foreach t in array array[
    'pocket_access','pocket_project_month','pocket_project_summary','pocket_forecast',
    'pocket_pricing','pocket_model_health','pocket_decision_summary_v2','pocket_alerts',
    'pocket_market_project','pocket_system_health_v2'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('revoke all on public.%I from authenticated', t);
  end loop;
end $$;

grant select on public.pocket_access to authenticated;
grant select on public.pocket_project_month to authenticated;
grant select on public.pocket_project_summary to authenticated;
grant select on public.pocket_forecast to authenticated;
grant select on public.pocket_pricing to authenticated;
grant select on public.pocket_model_health to authenticated;
grant select on public.pocket_decision_summary_v2 to authenticated;
grant select on public.pocket_alerts to authenticated;
grant select on public.pocket_market_project to authenticated;
grant select on public.pocket_system_health_v2 to authenticated;

create policy pocket_access_self
on public.pocket_access for select to authenticated
using (user_id = (select auth.uid()) and active);

do $$
declare t text;
begin
  foreach t in array array[
    'pocket_project_month','pocket_project_summary','pocket_forecast','pocket_pricing',
    'pocket_model_health','pocket_decision_summary_v2','pocket_alerts',
    'pocket_market_project','pocket_system_health_v2'
  ] loop
    execute format(
      'create policy %I on public.%I for select to authenticated using (exists (select 1 from public.pocket_access pa where pa.user_id = (select auth.uid()) and pa.active))',
      t || '_read', t
    );
  end loop;
end $$;

commit;
