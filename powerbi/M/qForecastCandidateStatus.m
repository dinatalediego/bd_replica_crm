let
    Source = PostgreSQL.Database(
        pPostgresServer,
        pPostgresDatabase,
        [Query = Text.Combine({
            "WITH latest AS (SELECT * FROM model_control.commercial_forecast_runs",
            "ORDER BY created_at DESC, run_id DESC LIMIT 1)",
            "SELECT p.run_id::text AS run_id, p.model,",
            "count(DISTINCT p.project) AS projects_with_candidate,",
            "count(*) FILTER (WHERE p.is_selected) AS selected_projects,",
            "k.candidate_projects AS accepted_validation_projects,",
            "CASE WHEN p.model IN ('gmm_analog','random_forest')",
            "THEN (r.manifest->'final_training'->>'train_rows')::integer END AS pooled_training_rows,",
            "r.selected_model, r.evidence_level,",
            "r.created_at AT TIME ZONE 'America/Lima' AS created_at_lima",
            "FROM latest r JOIN analytics.commercial_forecast_predictions p USING (run_id)",
            "LEFT JOIN LATERAL jsonb_to_recordset(coalesce(r.manifest->'selection_policy'->'rankings','[]'::jsonb))",
            "AS k(model text, candidate_projects integer) ON k.model = p.model",
            "WHERE p.horizon = 6",
            "GROUP BY p.run_id, p.model, k.candidate_projects, r.manifest,",
            "r.selected_model, r.evidence_level, r.created_at"
        }, " ")]
    ),
    Types = Table.TransformColumnTypes(Source, {
        {"projects_with_candidate", Int64.Type},
        {"selected_projects", Int64.Type},
        {"accepted_validation_projects", Int64.Type},
        {"pooled_training_rows", Int64.Type},
        {"created_at_lima", type datetime}
    })
in
    Types
