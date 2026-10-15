let
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase),
    Audience = Source{[Schema="analytics", Item="marketing_audiencias"]}[Data]
in
    Audience
