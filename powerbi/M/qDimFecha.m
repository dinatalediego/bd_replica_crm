let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "analytics", Item = "dim_fecha"]}[Data]
in
    Data
