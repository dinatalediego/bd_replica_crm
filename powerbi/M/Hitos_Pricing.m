let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "analytics", Item = "v_hitos_pricing"]}[Data]
in
    Data
