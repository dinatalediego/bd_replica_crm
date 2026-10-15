let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "SELECT run_id::text AS run_id, project, origin, horizon, model,",
            "forecast_month, prediction, monthly_prediction, stock, stock_remaining,",
            "lower80, upper80, lower95, upper95, evidence_level,",
            "created_at AT TIME ZONE 'America/Lima' AS created_at_lima",
            "FROM analytics.v_commercial_forecast_monthly"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"origin", type date},
        {"forecast_month", type date},
        {"horizon", Int64.Type},
        {"prediction", type number},
        {"monthly_prediction", type number},
        {"stock", type number},
        {"stock_remaining", type number},
        {"lower80", type number},
        {"upper80", type number},
        {"lower95", type number},
        {"upper95", type number},
        {"created_at_lima", type datetime}
    })
in
    Types
