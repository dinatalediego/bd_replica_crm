-- Medallio Pocket PROD hardening: require MFA (AAL2) for every mobile read.
-- Apply after 001_schema.sql.

begin;

revoke all on schema public from public;
revoke all on schema public from anon;
grant usage on schema public to authenticated;

do $$
declare t text;
begin
  foreach t in array array[
    'pocket_access','pocket_project_month','pocket_project_summary','pocket_forecast',
    'pocket_pricing','pocket_model_health','pocket_decision_summary_v2','pocket_alerts',
    'pocket_market_project','pocket_system_health_v2'
  ] loop
    execute format(
      'create policy %I on public.%I as restrictive for select to authenticated using ((select auth.jwt()->>''aal'') = ''aal2'')',
      t || '_mfa_required', t
    );
  end loop;
end $$;

commit;
