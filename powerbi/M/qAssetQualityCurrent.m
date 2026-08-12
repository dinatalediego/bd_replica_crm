let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = "SELECT * FROM observability.v_asset_quality_current"]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"quality_snapshot_at", type datetimezone},
            {"quality_score", type number},
            {"rows_source", Int64.Type},
            {"rows_target", Int64.Type},
            {"row_difference", Int64.Type},
            {"row_difference_pct", type number}
        }
    )
in
    Types
