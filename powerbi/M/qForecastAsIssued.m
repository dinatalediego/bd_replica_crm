let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "SELECT p.run_id::text AS run_id, p.project, p.origin, p.horizon, p.model,",
            "p.created_at AT TIME ZONE 'America/Lima' AS created_at_lima,",
            "p.prediction, p.stock, p.actual, p.error, p.absolute_error,",
            "p.eligible_scope, p.eligibility_reason, p.outcome_snapshot_id::text AS outcome_snapshot_id,",
            "p.measured_at AT TIME ZONE 'America/Lima' AS measured_at_lima,",
            "p.issued_before_window_start, p.issued_before_outcome_end,",
            "p.eligible_for_operational_scoring, p.eligible_for_strict_prospective_scoring,",
            "p.issuance_delay_days, p.covered80, p.covered95, p.evidence_level",
            "FROM analytics.v_commercial_forecast_performance p WHERE p.is_selected"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"origin", type date},
        {"horizon", Int64.Type},
        {"created_at_lima", type datetime},
        {"measured_at_lima", type datetime},
        {"prediction", type number},
        {"stock", type number},
        {"actual", type number},
        {"error", type number},
        {"absolute_error", type number},
        {"eligible_scope", type logical},
        {"issued_before_window_start", type logical},
        {"issued_before_outcome_end", type logical},
        {"eligible_for_operational_scoring", type logical},
        {"eligible_for_strict_prospective_scoring", type logical},
        {"covered80", type logical},
        {"covered95", type logical},
        {"issuance_delay_days", type number}
    })
in
    Types
