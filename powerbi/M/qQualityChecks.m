let
    Days = Number.ToText(Number.RoundDown(pDaysHistory), "0"),
    Sql = "
        SELECT *
        FROM observability.v_quality_checks
        WHERE checked_at >= now() - interval '" & Days & " days'
    ",
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase, [Query = Sql]),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"quality_check_id", Int64.Type},
            {"snapshot_id", Int64.Type},
            {"checked_at", type datetimezone},
            {"metric_value", type number},
            {"threshold_value", type number}
        }
    ),
    AddDate = Table.AddColumn(Types, "check_date", each Date.From([checked_at]), type date)
in
    AddDate
