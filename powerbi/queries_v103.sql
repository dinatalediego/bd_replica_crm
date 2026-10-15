-- 01 Evidence Calendar
SELECT *
FROM analytics.v_pbi_forecast_evidence_calendar_v103;

-- 02 Portfolio Model Scoreboard
SELECT *
FROM analytics.v_pbi_forecast_model_scoreboard_v103;

-- 03 Project Model Scoreboard
SELECT *
FROM analytics.v_pbi_forecast_project_scoreboard_v103;

-- 04 Champion / Challenger status
SELECT *
FROM analytics.v_pbi_forecast_champion_status_v103;

-- 05 CEO Predictive Evidence Status
SELECT *
FROM analytics.v_pbi_forecast_ceo_evidence_status_v103;

-- 06 Maturity Cycle observability
SELECT *
FROM analytics.v_pbi_forecast_maturity_cycles_v103;

-- Keep v1.0.2 monthly forecast surface as the detailed forecast fact
SELECT *
FROM analytics.v_pbi_forecast_monthly_current_v102;
