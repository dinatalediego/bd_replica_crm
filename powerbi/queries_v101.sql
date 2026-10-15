-- Current canonical forecasts, with explicit horizon/window semantics.
SELECT *
FROM analytics.v_pbi_forecast_factory_current_v101;

-- Model performance and defendability.
SELECT *
FROM analytics.v_pbi_forecast_performance_v101;

-- Run compliance including interval incubation.
SELECT *
FROM model_control.v_forecast_run_contract_compliance_v101;
