-- 01. Monthly forecasts + maturity
SELECT *
FROM analytics.v_pbi_forecast_monthly_current_v102;

-- 02. Prospective issuance clock
SELECT *
FROM analytics.v_pbi_forecast_issuance_clock_v102;

-- 03. Lead-time performance + defendability
SELECT *
FROM analytics.v_pbi_forecast_lead_time_performance_v102;

-- 04. Adapter audit
SELECT *
FROM analytics.v_pbi_forecast_adapter_audit_v102;

-- 05. Actual revisions
SELECT *
FROM analytics.forecast_actual_revision_v102;

-- 06. Scope compatibility
SELECT *
FROM analytics.forecast_scope_compatibility_v102;
