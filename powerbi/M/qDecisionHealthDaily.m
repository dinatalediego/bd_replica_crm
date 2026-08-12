let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = "SELECT * FROM observability.v_decision_health_daily"]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"decision_date", type date},
            {"recommendations", Int64.Type},
            {"actions", Int64.Type},
            {"outcomes", Int64.Type},
            {"expected_incremental_value", Currency.Type},
            {"action_cost", Currency.Type},
            {"realized_value", Currency.Type},
            {"adoption_rate", Percentage.Type},
            {"realized_roi", Percentage.Type}
        }
    )
in
    Types
