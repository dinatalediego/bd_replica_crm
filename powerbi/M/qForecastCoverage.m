let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "SELECT c.run_id::text AS run_id, c.project, c.status, c.stock,",
            "c.history_months, c.review_months, c.has_forecast, c.selected_model,",
            "c.horizon, c.forecast_cumulative, r.manifest->>'origin' AS origin,",
            "r.created_at AT TIME ZONE 'America/Lima' AS created_at_lima",
            "FROM analytics.v_commercial_forecast_coverage c",
            "JOIN model_control.commercial_forecast_runs r USING (run_id)"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"stock", type number},
        {"forecast_cumulative", type number},
        {"history_months", Int64.Type},
        {"review_months", Int64.Type},
        {"has_forecast", type logical},
        {"horizon", Int64.Type},
        {"origin", type date},
        {"created_at_lima", type datetime}
    })
in
    Types
