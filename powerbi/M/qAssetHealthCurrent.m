let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [
            Query = "
                SELECT *
                FROM observability.v_asset_health_current
                WHERE enabled = true
            "
        ]
    ),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"snapshot_at", type datetimezone},
            {"last_run_started_at", type datetimezone},
            {"last_run_finished_at", type datetimezone},
            {"last_success_at", type datetimezone},
            {"source_watermark_at", type datetimezone},
            {"target_watermark_at", type datetimezone},
            {"minutes_since_success", type number},
            {"replication_lag_minutes", type number},
            {"operational_health_score", type number},
            {"quality_score", type number},
            {"rows_last_run", Int64.Type},
            {"rows_source", Int64.Type},
            {"rows_target", Int64.Type},
            {"row_difference", Int64.Type}
        }
    )
in
    Types
