let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = "SELECT * FROM decision_intelligence.v_lead_action_outcome_performance"]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"decision_date", type date},
            {"recommendations", Int64.Type},
            {"actions_recorded", Int64.Type},
            {"sep_matured", Int64.Type},
            {"sep_rate", Percentage.Type},
            {"minuta_matured", Int64.Type},
            {"minuta_rate", Percentage.Type},
            {"total_action_cost", Currency.Type}
        }
    )
in
    Types
