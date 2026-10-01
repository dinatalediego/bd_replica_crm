let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "analytics", Item = "v_supuestos_absorcion"]}[Data]
in
    Data
