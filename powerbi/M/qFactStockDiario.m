let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [CreateNavigationProperties = false]
    ),
    Data = Source{[Schema = "analytics", Item = "fact_stock_ofertado_diario"]}[Data]
in
    Data
