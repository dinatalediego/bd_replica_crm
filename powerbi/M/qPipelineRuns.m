let
    Days = Number.ToText(Number.RoundDown(pDaysHistory), "0"),
    Sql = "
        SELECT *
        FROM observability.v_pipeline_runs
        WHERE started_at >= now() - interval '" & Days & " days'
    ",
    Source = PostgreSQL.Database(pPostgresServer, pPostgresDatabase, [Query = Sql]),
    Types = Table.TransformColumnTypes(
        Source,
        {
            {"started_at", type datetimezone},
            {"finished_at", type datetimezone},
            {"rows_extracted", Int64.Type},
            {"rows_loaded", Int64.Type},
            {"duration_minutes", type number},
            {"success_flag", Int64.Type}
        }
    ),
    AddDate = Table.AddColumn(Types, "run_date", each Date.From([started_at]), type date)
in
    AddDate
