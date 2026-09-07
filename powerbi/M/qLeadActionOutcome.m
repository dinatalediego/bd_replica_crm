let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = "SELECT * FROM decision_intelligence.v_lead_action_outcome"]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"decision_date", type date},
            {"scored_at", type datetimezone},
            {"priority_score", type number},
            {"p_minuta_60d", Percentage.Type},
            {"action_at", type datetimezone},
            {"action_cost", Currency.Type},
            {"separacion_14d", Int64.Type},
            {"separacion_observed_at", type datetimezone},
            {"minuta_60d", Int64.Type},
            {"minuta_observed_at", type datetimezone}
        }
    )
in
    Types
