-- v2.7.2 validation: must return one row per project and comparable real metrics.
SELECT
    count(*) AS proyectos,
    count(*) FILTER (WHERE latest_complete_period IS NOT NULL) AS con_mes_completo,
    count(*) FILTER (WHERE stock_units IS NOT NULL) AS con_stock,
    count(*) FILTER (WHERE absorption_rate IS NOT NULL) AS con_absorcion_3m,
    count(*) FILTER (WHERE gap_value IS NOT NULL) AS con_gap_economico,
    count(*) FILTER (WHERE forecast_units IS NOT NULL) AS con_forecast_h1,
    count(*) FILTER (WHERE forecast_wape_pct IS NOT NULL) AS con_wape_maduro
FROM analytics.v_project_growth_state;

SELECT project_key, count(*)
FROM analytics.v_project_growth_state
GROUP BY project_key
HAVING count(*) <> 1;

SELECT
    project_key,
    project_name,
    latest_complete_period,
    stock_units,
    last_complete_sales_units,
    sales_units,
    absorption_rate,
    months_to_zero,
    target_value,
    gap_value,
    forecast_units,
    forecast_wape_pct,
    attention_score,
    suggested_action,
    suggested_owner,
    suggested_urgency
FROM analytics.v_project_growth_state
ORDER BY attention_score DESC, gap_value DESC NULLS LAST, project_key;

SELECT
    project_key,
    project_name,
    decision,
    owner,
    urgency,
    value_at_stake_soles,
    value_at_stake_type,
    why,
    outcome_required,
    roi_required
FROM decision_intelligence.v_ceo_growth_decision_queue
LIMIT 10;
