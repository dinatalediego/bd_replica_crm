let
    Days = Number.ToText(Number.RoundDown(pDaysHistory), "0"),
    Sql = "
        SELECT
            snapshot_id,
            snapshot_at,
            mode,
            asset_key,
            last_run_status,
            last_success_at,
            minutes_since_success,
            rows_last_run,
            rows_source,
            rows_target,
            row_difference,
            row_difference_pct,
            source_watermark_at,
            target_watermark_at,
            replication_lag_minutes,
            freshness_status,
            replication_status,
            pipeline_status,
            health_status,
            operational_health_score,
            quality_score
        FROM observability.asset_snapshots
        WHERE snapshot_at >= now() - interval '" & Days & " days'
    ",
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase, [Query = Sql]),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"snapshot_id", Int64.Type},
            {"snapshot_at", type datetimezone},
            {"last_success_at", type datetimezone},
            {"source_watermark_at", type datetimezone},
            {"target_watermark_at", type datetimezone},
            {"minutes_since_success", type number},
            {"replication_lag_minutes", type number},
            {"row_difference_pct", type number},
            {"operational_health_score", type number},
            {"quality_score", type number}
        }
    ),
    AddDate = Table.AddColumn(Types, "snapshot_date", each Date.From([snapshot_at]), type date)
in
    AddDate
