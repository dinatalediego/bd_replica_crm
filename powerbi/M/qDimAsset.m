let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [
            Query = "
                SELECT
                    asset_key,
                    source_schema,
                    source_table,
                    target_schema,
                    target_table,
                    layer,
                    enabled,
                    criticality,
                    business_domain,
                    business_process,
                    business_owner,
                    business_impact,
                    downstream_products,
                    expected_frequency_minutes,
                    freshness_sla_minutes,
                    replication_lag_sla_minutes,
                    strategy,
                    watermark_column
                FROM observability.asset_registry
            "
        ]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"asset_key", type text},
            {"enabled", type logical},
            {"expected_frequency_minutes", Int64.Type},
            {"freshness_sla_minutes", Int64.Type},
            {"replication_lag_sla_minutes", Int64.Type}
        }
    )
in
    Types
