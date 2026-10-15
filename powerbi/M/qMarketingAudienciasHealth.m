let
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase),
    Health = Source{[Schema="analytics", Item="v_marketing_audiencias_health"]}[Data]
in
    Health
