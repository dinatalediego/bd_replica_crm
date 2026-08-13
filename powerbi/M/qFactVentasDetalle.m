let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "analytics", Item = "fact_ventas_detalle"]}[Data]
in
    Data
