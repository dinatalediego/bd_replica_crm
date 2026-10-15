let
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase),
    Audience = Source{[Schema="analytics", Item="v_marketing_positiva"]}[Data]
in
    Audience
