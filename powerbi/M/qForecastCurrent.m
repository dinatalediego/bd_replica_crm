let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "SELECT p.run_id::text AS run_id, p.project, p.origin, p.horizon,",
            "p.model, p.prediction, p.stock, p.stock_remaining,",
            "p.lower80, p.upper80, p.lower95, p.upper95,",
            "p.target_sales, p.expected_shortfall, p.owner, p.recommendation,",
            "p.evidence_level, p.created_at AT TIME ZONE 'America/Lima' AS created_at_lima",
            "FROM analytics.v_commercial_forecast_current p WHERE p.is_selected"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"origin", type date},
        {"horizon", Int64.Type},
        {"prediction", type number},
        {"stock", type number},
        {"stock_remaining", type number},
        {"lower80", type number},
        {"upper80", type number},
        {"lower95", type number},
        {"upper95", type number},
        {"target_sales", type number},
        {"expected_shortfall", type number},
        {"created_at_lima", type datetime}
    })
in
    Types
