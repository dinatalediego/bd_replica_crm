let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "observability", Item = "v_absorption_reconciliation_current"]}[Data]
in
    Data
