-- Monthly projection derived from cumulative horizons for Power BI.
-- The source prediction is cumulative; monthly_prediction is the increment.
CREATE OR REPLACE VIEW analytics.v_commercial_forecast_monthly AS
WITH ordered AS (
    SELECT
        p.run_id,
        p.project,
        p.origin,
        p.horizon,
        p.model,
        p.prediction,
        p.stock,
        p.stock_remaining,
        p.lower80,
        p.upper80,
        p.lower95,
        p.upper95,
        p.evidence_level,
        p.created_at,
        p.prediction - COALESCE(
            LAG(p.prediction) OVER (
                PARTITION BY p.run_id, p.project, p.model
                ORDER BY p.horizon
            ), 0
        ) AS monthly_prediction
    FROM analytics.v_commercial_forecast_current p
    WHERE p.is_selected
)
SELECT
    run_id,
    project,
    origin,
    horizon,
    model,
    origin + (horizon * INTERVAL '1 month') AS forecast_month,
    prediction,
    monthly_prediction,
    stock,
    stock_remaining,
    lower80,
    upper80,
    lower95,
    upper95,
    evidence_level,
    created_at
FROM ordered;
