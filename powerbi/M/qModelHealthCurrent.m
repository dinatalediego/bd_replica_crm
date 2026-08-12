let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = "SELECT * FROM observability.v_model_health_current"]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"trained_at", type datetimezone},
            {"training_window_from", type datetimezone},
            {"training_window_to", type datetimezone},
            {"last_scored_at", type datetimezone},
            {"data_as_of", type datetimezone},
            {"rows_scored", Int64.Type},
            {"drift_score", type number},
            {"model_age_hours", type number},
            {"feature_freshness_minutes", type number}
        }
    )
in
    Types
