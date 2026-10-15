let
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase),
    Audience = Source{[Schema="analytics", Item="v_marketing_negativa_sin_avance"]}[Data]
in
    Audience
