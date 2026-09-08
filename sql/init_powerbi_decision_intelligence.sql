-- Power BI Decision Intelligence semantic layer.
-- PostgreSQL local / medallio_dw.
--
-- Objetivo:
--   entregar a Power BI vistas de presentacion ya resueltas para
--   funnel, policy, capacidad, adopcion, experimento, ejecucion comercial,
--   monitoreo de modelos y valor economico.
--
-- Principios:
--   * no reimplementa el scoring;
--   * no ejecuta acciones comerciales;
--   * no borra ni modifica recomendaciones legacy;
--   * conserva lineage evidence -> score -> policy -> experiment -> action -> outcome;
--   * diferencia performance observacional de evidencia causal.

BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;

-- ============================================================================
-- BLOCK 01. Policy / experiment registry
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_policy_registry AS
WITH experiment_policies AS (
    SELECT
        e.experiment_id::text AS experiment_id,
        e.experiment_name,
        e.status AS experiment_status,
        e.started_at,
        e.ended_at,
        COALESCE(NULLIF(e.design_json->>'policy_id', ''), 'legacy_unversioned') AS policy_id,
        NULLIF(e.design_json->>'policy_version', '') AS policy_version,
        CASE
            WHEN COALESCE(e.design_json->>'treatment_share', '') ~ '^[0-9]+(\.[0-9]+)?$'
                THEN (e.design_json->>'treatment_share')::double precision
        END AS treatment_share,
        CASE
            WHEN COALESCE(e.design_json->>'daily_capacity', '') ~ '^[0-9]+$'
                THEN (e.design_json->>'daily_capacity')::integer
        END AS daily_capacity,
        CASE
            WHEN COALESCE(e.design_json->>'max_lead_age_days', '') ~ '^[0-9]+$'
                THEN (e.design_json->>'max_lead_age_days')::integer
        END AS max_lead_age_days,
        COALESCE(e.design_json->'allowed_bands', '["A","B"]'::jsonb) AS allowed_bands,
        e.primary_outcome,
        e.causal_estimand,
        false AS is_default_only
    FROM experiments.experiments e
    WHERE e.decision_system = 'priorizacion_leads'
)
SELECT *
FROM experiment_policies
UNION ALL
SELECT
    NULL::text AS experiment_id,
    'lead_priority_v2_pilot'::text AS experiment_name,
    'NOT_CREATED'::text AS experiment_status,
    NULL::timestamptz AS started_at,
    NULL::timestamptz AS ended_at,
    'lead_priority_v2'::text AS policy_id,
    '2.0'::text AS policy_version,
    0.80::double precision AS treatment_share,
    100::integer AS daily_capacity,
    7::integer AS max_lead_age_days,
    '["A","B"]'::jsonb AS allowed_bands,
    'minuta_60d'::text AS primary_outcome,
    'ITT: E[Y|assignment=treatment] - E[Y|assignment=control]'::text AS causal_estimand,
    true AS is_default_only
WHERE NOT EXISTS (
    SELECT 1
    FROM experiment_policies p
    WHERE p.policy_id = 'lead_priority_v2'
);

COMMENT ON VIEW analytics.v_pbi_policy_registry IS
'Power BI policy/experiment registry. Uses experiment design_json and exposes a safe lead_priority_v2 default before the pilot is persisted.';

-- ============================================================================
-- BLOCK 02. Recommendation-grain closed-loop journey
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_policy_journey AS
WITH rec_base AS (
    SELECT
        r.recommendation_id,
        r.decision_system,
        r.entity_id AS evidence_key,
        r.scored_at,
        r.model_run_id,
        r.predicted_probability,
        r.expected_value_no_action,
        r.expected_incremental_value,
        r.expected_value_with_action,
        r.recommended_action,
        r.priority_rank AS recommendation_priority_rank,
        r.context_json,
        COALESCE(NULLIF(r.context_json->>'policy_id', ''), 'legacy_unversioned') AS policy_id,
        NULLIF(r.context_json->>'policy_version', '') AS policy_version,
        NULLIF(r.context_json->>'experiment_id', '') AS experiment_id,
        NULLIF(r.context_json->>'treatment_group', '') AS context_treatment_group,
        NULLIF(r.context_json->>'score_id', '') AS score_id,
        NULLIF(r.context_json->>'lead_id', '') AS context_lead_id,
        NULLIF(r.context_json->>'priority_band', '') AS context_priority_band,
        CASE
            WHEN COALESCE(r.context_json->>'priority_score', '') ~ '^-?[0-9]+(\.[0-9]+)?$'
                THEN (r.context_json->>'priority_score')::double precision
        END AS context_priority_score,
        CASE
            WHEN COALESCE(r.context_json->>'priority_rank', '') ~ '^[0-9]+$'
                THEN (r.context_json->>'priority_rank')::integer
        END AS context_priority_rank,
        CASE
            WHEN COALESCE(r.context_json->>'policy_rank', '') ~ '^[0-9]+$'
                THEN (r.context_json->>'policy_rank')::integer
        END AS policy_rank,
        NULLIF(r.context_json->>'codigo_proyecto', '') AS context_codigo_proyecto,
        NULLIF(r.context_json->>'asesor', '') AS context_asesor,
        NULLIF(r.context_json->>'canal', '') AS context_canal,
        NULLIF(r.context_json->>'medio', '') AS context_medio,
        NULLIF(r.context_json->>'action_owner_proposed', '') AS action_owner_proposed,
        CASE
            WHEN COALESCE(r.context_json->>'sla_minutes', '') ~ '^[0-9]+$'
                THEN (r.context_json->>'sla_minutes')::integer
        END AS context_sla_minutes,
        COALESCE(
            NULLIF(r.context_json->>'recommended_at', '')::timestamptz,
            r.scored_at
        ) AS recommended_at,
        NULLIF(r.context_json->>'expires_at', '')::timestamptz AS expires_at
    FROM decision_intelligence.recommendations r
    WHERE r.decision_system = 'priorizacion_leads'
)
SELECT
    rb.recommendation_id::text AS recommendation_id,
    rb.evidence_key,
    COALESCE(rb.context_lead_id, s.lead_id, e.lead_id) AS lead_id,
    rb.decision_system,
    rb.policy_id,
    rb.policy_version,
    rb.experiment_id,
    COALESCE(rb.context_treatment_group, ass.treatment_group) AS treatment_group,
    exp.experiment_name,
    exp.status AS experiment_status,
    rb.model_run_id::text AS model_run_id,
    mr.model_name,
    mr.model_version,
    mr.status AS model_status,
    s.is_provisional,
    rb.score_id,
    COALESCE(s.decision_at, e.decision_at) AS decision_at,
    COALESCE(s.scored_at, rb.scored_at) AS scored_at,
    rb.recommended_at,
    rb.recommended_at::date AS recommendation_date,
    rb.expires_at,
    COALESCE(rb.context_codigo_proyecto, e.codigo_proyecto) AS codigo_proyecto,
    COALESCE(rb.context_asesor, e.asesor) AS asesor,
    COALESCE(rb.context_canal, e.canal) AS canal,
    COALESCE(rb.context_medio, e.medio) AS medio,
    e.evidence_source,
    e.label_status,
    COALESCE(rb.context_priority_band, s.priority_band) AS priority_band,
    COALESCE(rb.context_priority_score, s.priority_score) AS priority_score,
    COALESCE(rb.context_priority_rank, s.priority_rank) AS model_priority_rank,
    rb.policy_rank,
    rb.recommendation_priority_rank,
    COALESCE(s.p_separacion_14d, NULLIF(rb.context_json->>'p_separacion_14d', '')::double precision) AS p_separacion_14d,
    COALESCE(s.p_minuta_60d, rb.predicted_probability) AS p_minuta_60d,
    rb.recommended_action,
    rb.action_owner_proposed,
    COALESCE(
        rb.context_sla_minutes,
        CASE COALESCE(rb.context_priority_band, s.priority_band)
            WHEN 'A' THEN 15
            WHEN 'B' THEN 60
            WHEN 'C' THEN 1440
            WHEN 'D' THEN 1440
        END
    ) AS sla_minutes,
    act.action_id::text AS action_id,
    act.action_taken,
    act.action_owner,
    act.action_at,
    act.action_cost AS first_action_cost,
    COALESCE(actagg.action_event_count, 0)::bigint AS action_event_count,
    COALESCE(actagg.total_action_cost, 0)::numeric(18,4) AS total_action_cost,
    (act.action_id IS NOT NULL) AS action_adopted,
    CASE
        WHEN act.action_id IS NULL THEN NULL
        ELSE act.action_taken = rb.recommended_action
    END AS followed_recommendation,
    CASE
        WHEN act.action_at IS NULL THEN NULL
        ELSE EXTRACT(EPOCH FROM (act.action_at - rb.recommended_at)) / 60.0
    END AS minutes_to_action,
    CASE
        WHEN act.action_at IS NULL THEN NULL
        WHEN COALESCE(
            rb.context_sla_minutes,
            CASE COALESCE(rb.context_priority_band, s.priority_band)
                WHEN 'A' THEN 15
                WHEN 'B' THEN 60
                WHEN 'C' THEN 1440
                WHEN 'D' THEN 1440
            END
        ) IS NULL THEN NULL
        ELSE
            EXTRACT(EPOCH FROM (act.action_at - rb.recommended_at)) / 60.0
            <= COALESCE(
                rb.context_sla_minutes,
                CASE COALESCE(rb.context_priority_band, s.priority_band)
                    WHEN 'A' THEN 15
                    WHEN 'B' THEN 60
                    WHEN 'C' THEN 1440
                    WHEN 'D' THEN 1440
                END
            )
    END AS within_sla,
    outc.separacion_14d,
    outc.separacion_observed_at,
    outc.separacion_realized_value,
    (outc.separacion_14d IS NOT NULL) AS separacion_matured,
    outc.minuta_60d,
    outc.minuta_observed_at,
    outc.minuta_realized_value,
    (outc.minuta_60d IS NOT NULL) AS minuta_matured,
    rb.expected_value_no_action,
    rb.expected_incremental_value,
    rb.expected_value_with_action,
    CASE WHEN act.action_id IS NOT NULL THEN 1 ELSE 0 END AS action_adopted_flag,
    CASE WHEN outc.separacion_14d IS NOT NULL THEN 1 ELSE 0 END AS separacion_matured_flag,
    CASE WHEN outc.minuta_60d IS NOT NULL THEN 1 ELSE 0 END AS minuta_matured_flag
FROM rec_base rb
LEFT JOIN features.lead_evidence e
    ON e.evidence_key = rb.evidence_key
LEFT JOIN decision_intelligence.lead_scores s
    ON s.score_id::text = rb.score_id
LEFT JOIN model_control.model_runs mr
    ON mr.model_run_id = rb.model_run_id
LEFT JOIN experiments.assignments ass
    ON ass.entity_id = rb.evidence_key
   AND ass.experiment_id::text = rb.experiment_id
LEFT JOIN experiments.experiments exp
    ON exp.experiment_id::text = rb.experiment_id
LEFT JOIN LATERAL (
    SELECT a1.*
    FROM decision_intelligence.actions a1
    WHERE a1.recommendation_id = rb.recommendation_id
    ORDER BY a1.action_at
    LIMIT 1
) act ON true
LEFT JOIN LATERAL (
    SELECT
        COUNT(*)::bigint AS action_event_count,
        COALESCE(SUM(a2.action_cost), 0)::numeric(18,4) AS total_action_cost
    FROM decision_intelligence.actions a2
    WHERE a2.recommendation_id = rb.recommendation_id
) actagg ON true
LEFT JOIN LATERAL (
    SELECT
        MAX(o.outcome_value) FILTER (WHERE o.outcome_name = 'separacion_14d') AS separacion_14d,
        MAX(o.outcome_at) FILTER (WHERE o.outcome_name = 'separacion_14d') AS separacion_observed_at,
        MAX(o.realized_value) FILTER (WHERE o.outcome_name = 'separacion_14d') AS separacion_realized_value,
        MAX(o.outcome_value) FILTER (WHERE o.outcome_name = 'minuta_60d') AS minuta_60d,
        MAX(o.outcome_at) FILTER (WHERE o.outcome_name = 'minuta_60d') AS minuta_observed_at,
        MAX(o.realized_value) FILTER (WHERE o.outcome_name = 'minuta_60d') AS minuta_realized_value
    FROM decision_intelligence.outcomes o
    WHERE o.decision_system = rb.decision_system
      AND o.entity_id = rb.evidence_key
) outc ON true;

COMMENT ON VIEW analytics.v_pbi_policy_journey IS
'Power BI recommendation-grain closed-loop fact: model/score, policy, experiment assignment, recommendation, first action, SLA, costs and matured outcomes.';

-- Optional Power BI parameterization without rebuilding logic in Power Query.
CREATE OR REPLACE FUNCTION analytics.fn_pbi_decision_window(
    p_from_date date DEFAULT (CURRENT_DATE - 90),
    p_to_date date DEFAULT CURRENT_DATE,
    p_policy_id text DEFAULT NULL,
    p_project text DEFAULT NULL
)
RETURNS SETOF analytics.v_pbi_policy_journey
LANGUAGE sql
STABLE
AS $$
    SELECT j.*
    FROM analytics.v_pbi_policy_journey j
    WHERE j.recommendation_date BETWEEN p_from_date AND p_to_date
      AND (p_policy_id IS NULL OR j.policy_id = p_policy_id)
      AND (p_project IS NULL OR j.codigo_proyecto = p_project)
$$;

COMMENT ON FUNCTION analytics.fn_pbi_decision_window(date,date,text,text) IS
'Parameterized recommendation-grain Power BI window. Filters date, policy and project server-side.';

-- ============================================================================
-- BLOCK 03. Parameterized funnel + default Power BI funnel view
-- ============================================================================

CREATE OR REPLACE FUNCTION analytics.fn_pbi_policy_funnel(
    p_policy_id text DEFAULT 'lead_priority_v2',
    p_lookback_days integer DEFAULT 7
)
RETURNS TABLE (
    policy_id text,
    lookback_days integer,
    stage_order integer,
    stage_key text,
    stage_label text,
    stage_rows bigint,
    prior_stage_rows bigint,
    conversion_from_prior double precision,
    as_of_ts timestamptz
)
LANGUAGE sql
STABLE
AS $$
WITH serving_scores AS (
    SELECT DISTINCT ON (s.evidence_key)
        s.evidence_key,
        s.priority_band,
        s.priority_score,
        s.priority_rank,
        s.scored_at,
        e.decision_at,
        e.evidence_source,
        e.label_status
    FROM decision_intelligence.lead_scores s
    JOIN features.lead_evidence e USING (evidence_key)
    JOIN model_control.model_runs mr
      ON mr.model_run_id = s.model_run_id
    JOIN model_control.model_aliases a
      ON a.model_run_id = s.model_run_id
     AND a.decision_system = mr.decision_system
     AND a.model_name = mr.model_name
     AND a.alias_name = 'serving'
    WHERE mr.decision_system = 'priorizacion_leads'
    ORDER BY s.evidence_key, s.scored_at DESC
),
eligible AS (
    SELECT *
    FROM serving_scores
    WHERE evidence_source = 'LIVE'
      AND label_status = 'PENDING'
      AND priority_band IN ('A','B')
      AND decision_at >= CURRENT_TIMESTAMP - (GREATEST(p_lookback_days, 1) * interval '1 day')
),
policy_experiments AS (
    SELECT e.experiment_id
    FROM experiments.experiments e
    WHERE e.decision_system = 'priorizacion_leads'
      AND e.design_json->>'policy_id' = p_policy_id
),
assignment_counts AS (
    SELECT
        COUNT(*)::bigint AS assigned_n,
        COUNT(*) FILTER (WHERE a.treatment_group = 'TREATMENT')::bigint AS treatment_n,
        COUNT(*) FILTER (WHERE a.treatment_group = 'CONTROL')::bigint AS control_n
    FROM experiments.assignments a
    WHERE a.experiment_id IN (SELECT experiment_id FROM policy_experiments)
),
policy_recommendations AS (
    SELECT r.recommendation_id, r.entity_id
    FROM decision_intelligence.recommendations r
    WHERE r.decision_system = 'priorizacion_leads'
      AND r.context_json->>'policy_id' = p_policy_id
),
recommendation_counts AS (
    SELECT
        COUNT(*)::bigint AS recommendations_n,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM decision_intelligence.actions a
                WHERE a.recommendation_id = pr.recommendation_id
            )
        )::bigint AS actions_n,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM decision_intelligence.outcomes o
                WHERE o.decision_system = 'priorizacion_leads'
                  AND o.entity_id = pr.entity_id
                  AND o.outcome_name = 'separacion_14d'
                  AND o.outcome_value > 0
            )
        )::bigint AS sep_positive_n,
        COUNT(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM decision_intelligence.outcomes o
                WHERE o.decision_system = 'priorizacion_leads'
                  AND o.entity_id = pr.entity_id
                  AND o.outcome_name = 'minuta_60d'
                  AND o.outcome_value > 0
            )
        )::bigint AS minuta_positive_n
    FROM policy_recommendations pr
),
counts AS (
    SELECT
        (SELECT COUNT(*)::bigint FROM serving_scores) AS serving_n,
        (SELECT COUNT(*)::bigint FROM eligible) AS eligible_n,
        COALESCE((SELECT assigned_n FROM assignment_counts),0)::bigint AS assigned_n,
        COALESCE((SELECT treatment_n FROM assignment_counts),0)::bigint AS treatment_n,
        COALESCE((SELECT recommendations_n FROM recommendation_counts),0)::bigint AS recommendations_n,
        COALESCE((SELECT actions_n FROM recommendation_counts),0)::bigint AS actions_n,
        COALESCE((SELECT sep_positive_n FROM recommendation_counts),0)::bigint AS sep_positive_n,
        COALESCE((SELECT minuta_positive_n FROM recommendation_counts),0)::bigint AS minuta_positive_n
),
stages AS (
    SELECT *
    FROM counts c
    CROSS JOIN LATERAL (
        VALUES
            (1,'serving_scores','Scores serving',c.serving_n),
            (2,'eligible','Elegibles policy',c.eligible_n),
            (3,'assigned','Asignados piloto',c.assigned_n),
            (4,'treatment','Treatment',c.treatment_n),
            (5,'recommendations','Recomendaciones',c.recommendations_n),
            (6,'actions','Acciones',c.actions_n),
            (7,'separaciones','Separaciones positivas',c.sep_positive_n),
            (8,'minutas','Minutas positivas',c.minuta_positive_n)
    ) AS v(stage_order,stage_key,stage_label,stage_rows)
),
with_prior AS (
    SELECT
        s.*,
        LAG(s.stage_rows) OVER (ORDER BY s.stage_order) AS prior_stage_rows
    FROM stages s
)
SELECT
    p_policy_id,
    p_lookback_days,
    w.stage_order,
    w.stage_key,
    w.stage_label,
    w.stage_rows,
    w.prior_stage_rows,
    CASE
        WHEN w.prior_stage_rows IS NULL OR w.prior_stage_rows = 0 THEN NULL
        ELSE w.stage_rows::double precision / w.prior_stage_rows::double precision
    END AS conversion_from_prior,
    CURRENT_TIMESTAMP AS as_of_ts
FROM with_prior w
ORDER BY w.stage_order
$$;

COMMENT ON FUNCTION analytics.fn_pbi_policy_funnel(text,integer) IS
'Parameterized Power BI funnel. V2 eligibility semantics: LIVE + PENDING + bands A/B + lookback window.';

CREATE OR REPLACE VIEW analytics.v_pbi_policy_funnel AS
SELECT *
FROM analytics.fn_pbi_policy_funnel('lead_priority_v2', 7);

COMMENT ON VIEW analytics.v_pbi_policy_funnel IS
'Default lead_priority_v2 7-day Power BI funnel. Use fn_pbi_policy_funnel for parameterized policy/lookback.';

-- ============================================================================
-- BLOCK 04. Policy capacity / assignment
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_policy_capacity AS
WITH assignment_base AS (
    SELECT
        a.experiment_id::text AS experiment_id,
        e.experiment_name,
        e.status AS experiment_status,
        COALESCE(NULLIF(e.design_json->>'policy_id',''), 'legacy_unversioned') AS policy_id,
        NULLIF(e.design_json->>'policy_version','') AS policy_version,
        CASE
            WHEN COALESCE(e.design_json->>'daily_capacity','') ~ '^[0-9]+$'
                THEN (e.design_json->>'daily_capacity')::integer
        END AS daily_capacity,
        a.entity_id AS evidence_key,
        a.treatment_group,
        a.assigned_at,
        le.codigo_proyecto,
        le.asesor,
        ls.priority_band,
        ls.priority_score,
        ls.priority_rank
    FROM experiments.assignments a
    JOIN experiments.experiments e
      ON e.experiment_id = a.experiment_id
    LEFT JOIN features.lead_evidence le
      ON le.evidence_key = a.entity_id
    LEFT JOIN LATERAL (
        SELECT s.priority_band, s.priority_score, s.priority_rank
        FROM decision_intelligence.lead_scores s
        WHERE s.evidence_key = a.entity_id
          AND s.scored_at <= a.assigned_at
        ORDER BY s.scored_at DESC
        LIMIT 1
    ) ls ON true
    WHERE e.decision_system = 'priorizacion_leads'
),
grouped AS (
    SELECT
        assigned_at::date AS assignment_date,
        experiment_id,
        experiment_name,
        experiment_status,
        policy_id,
        policy_version,
        daily_capacity,
        codigo_proyecto,
        priority_band,
        COUNT(*)::bigint AS selected_n,
        COUNT(*) FILTER (WHERE treatment_group = 'TREATMENT')::bigint AS treatment_n,
        COUNT(*) FILTER (WHERE treatment_group = 'CONTROL')::bigint AS control_n,
        AVG(priority_score) AS avg_priority_score,
        MIN(priority_rank) AS best_priority_rank,
        MAX(priority_rank) AS worst_priority_rank
    FROM assignment_base
    GROUP BY
        assigned_at::date, experiment_id, experiment_name, experiment_status,
        policy_id, policy_version, daily_capacity, codigo_proyecto, priority_band
)
SELECT
    g.*,
    SUM(g.selected_n) OVER (
        PARTITION BY g.assignment_date, g.experiment_id
    )::bigint AS selected_day_n,
    CASE
        WHEN g.daily_capacity IS NULL OR g.daily_capacity = 0 THEN NULL
        ELSE
            SUM(g.selected_n) OVER (
                PARTITION BY g.assignment_date, g.experiment_id
            )::double precision / g.daily_capacity::double precision
    END AS capacity_utilization_day,
    CASE
        WHEN SUM(g.selected_n) OVER (
            PARTITION BY g.assignment_date, g.experiment_id
        ) = 0 THEN NULL
        ELSE g.selected_n::double precision
             / SUM(g.selected_n) OVER (
                 PARTITION BY g.assignment_date, g.experiment_id
             )::double precision
    END AS share_of_selected_day
FROM grouped g;

COMMENT ON VIEW analytics.v_pbi_policy_capacity IS
'Power BI assignment/capacity view by date, experiment, project and priority band.';

-- ============================================================================
-- BLOCK 05. Adoption / SLA
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_policy_adoption AS
SELECT
    j.recommendation_date,
    j.policy_id,
    j.policy_version,
    j.experiment_id,
    j.experiment_name,
    j.codigo_proyecto,
    COALESCE(j.asesor, 'SIN_ASESOR') AS asesor,
    j.priority_band,
    j.recommended_action,
    COUNT(*)::bigint AS recommendations,
    COUNT(*) FILTER (WHERE j.action_adopted)::bigint AS actions_recorded,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE COUNT(*) FILTER (WHERE j.action_adopted)::double precision / COUNT(*)::double precision
    END AS adoption_rate,
    COUNT(*) FILTER (WHERE j.followed_recommendation IS TRUE)::bigint AS followed_recommendation_n,
    CASE
        WHEN COUNT(*) FILTER (WHERE j.action_adopted) = 0 THEN NULL
        ELSE COUNT(*) FILTER (WHERE j.followed_recommendation IS TRUE)::double precision
             / COUNT(*) FILTER (WHERE j.action_adopted)::double precision
    END AS followed_recommendation_rate,
    COUNT(*) FILTER (WHERE j.within_sla IS TRUE)::bigint AS within_sla_n,
    CASE
        WHEN COUNT(*) FILTER (WHERE j.action_adopted) = 0 THEN NULL
        ELSE COUNT(*) FILTER (WHERE j.within_sla IS TRUE)::double precision
             / COUNT(*) FILTER (WHERE j.action_adopted)::double precision
    END AS within_sla_rate,
    AVG(j.minutes_to_action) FILTER (WHERE j.action_adopted) AS avg_minutes_to_action,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY j.minutes_to_action)
        FILTER (WHERE j.action_adopted) AS median_minutes_to_action,
    COUNT(*) FILTER (WHERE j.separacion_matured)::bigint AS sep_matured,
    AVG(j.separacion_14d) FILTER (WHERE j.separacion_matured) AS sep_rate,
    COUNT(*) FILTER (WHERE j.minuta_matured)::bigint AS minuta_matured,
    AVG(j.minuta_60d) FILTER (WHERE j.minuta_matured) AS minuta_rate,
    COALESCE(SUM(j.total_action_cost),0)::numeric(18,4) AS total_action_cost
FROM analytics.v_pbi_policy_journey j
GROUP BY
    j.recommendation_date, j.policy_id, j.policy_version,
    j.experiment_id, j.experiment_name, j.codigo_proyecto,
    COALESCE(j.asesor, 'SIN_ASESOR'), j.priority_band, j.recommended_action;

COMMENT ON VIEW analytics.v_pbi_policy_adoption IS
'Power BI policy adoption and SLA metrics by recommendation date, project, advisor, band and action.';

-- ============================================================================
-- BLOCK 06. Experiment / ITT performance
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_experiment_performance AS
WITH assignment_base AS (
    SELECT
        e.experiment_id::text AS experiment_id,
        e.experiment_name,
        e.status AS experiment_status,
        COALESCE(NULLIF(e.design_json->>'policy_id',''), 'legacy_unversioned') AS policy_id,
        NULLIF(e.design_json->>'policy_version','') AS policy_version,
        e.primary_outcome,
        e.causal_estimand,
        a.entity_id AS evidence_key,
        a.treatment_group,
        a.assigned_at,
        rec.recommendation_id,
        rec.action_id,
        outc.separacion_14d,
        outc.minuta_60d
    FROM experiments.assignments a
    JOIN experiments.experiments e
      ON e.experiment_id = a.experiment_id
    LEFT JOIN LATERAL (
        SELECT
            r.recommendation_id,
            act.action_id
        FROM decision_intelligence.recommendations r
        LEFT JOIN LATERAL (
            SELECT a1.action_id
            FROM decision_intelligence.actions a1
            WHERE a1.recommendation_id = r.recommendation_id
            ORDER BY a1.action_at
            LIMIT 1
        ) act ON true
        WHERE r.decision_system = e.decision_system
          AND r.entity_id = a.entity_id
          AND r.context_json->>'experiment_id' = e.experiment_id::text
        ORDER BY r.scored_at
        LIMIT 1
    ) rec ON true
    LEFT JOIN LATERAL (
        SELECT
            MAX(o.outcome_value) FILTER (WHERE o.outcome_name = 'separacion_14d') AS separacion_14d,
            MAX(o.outcome_value) FILTER (WHERE o.outcome_name = 'minuta_60d') AS minuta_60d
        FROM decision_intelligence.outcomes o
        WHERE o.decision_system = e.decision_system
          AND o.entity_id = a.entity_id
    ) outc ON true
    WHERE e.decision_system = 'priorizacion_leads'
),
long_outcomes AS (
    SELECT
        b.experiment_id,
        b.experiment_name,
        b.experiment_status,
        b.policy_id,
        b.policy_version,
        b.primary_outcome,
        b.causal_estimand,
        b.evidence_key,
        b.treatment_group,
        b.assigned_at,
        b.recommendation_id,
        b.action_id,
        v.outcome_name,
        v.outcome_value
    FROM assignment_base b
    CROSS JOIN LATERAL (
        VALUES
            ('separacion_14d'::text, b.separacion_14d),
            ('minuta_60d'::text, b.minuta_60d)
    ) AS v(outcome_name,outcome_value)
),
grouped AS (
    SELECT
        experiment_id,
        experiment_name,
        experiment_status,
        policy_id,
        policy_version,
        primary_outcome,
        causal_estimand,
        outcome_name,
        COUNT(*) FILTER (WHERE treatment_group = 'TREATMENT')::bigint AS treatment_assigned,
        COUNT(*) FILTER (WHERE treatment_group = 'CONTROL')::bigint AS control_assigned,
        COUNT(outcome_value) FILTER (WHERE treatment_group = 'TREATMENT')::bigint AS treatment_matured,
        COUNT(outcome_value) FILTER (WHERE treatment_group = 'CONTROL')::bigint AS control_matured,
        COALESCE(SUM(outcome_value) FILTER (WHERE treatment_group = 'TREATMENT'),0) AS treatment_positive,
        COALESCE(SUM(outcome_value) FILTER (WHERE treatment_group = 'CONTROL'),0) AS control_positive,
        AVG(outcome_value) FILTER (WHERE treatment_group = 'TREATMENT') AS treatment_rate,
        AVG(outcome_value) FILTER (WHERE treatment_group = 'CONTROL') AS control_rate,
        COUNT(recommendation_id) FILTER (WHERE treatment_group = 'TREATMENT')::bigint AS treatment_recommendations,
        COUNT(recommendation_id) FILTER (WHERE treatment_group = 'CONTROL')::bigint AS control_recommendations,
        COUNT(action_id) FILTER (WHERE treatment_group = 'TREATMENT')::bigint AS treatment_actions,
        COUNT(action_id) FILTER (WHERE treatment_group = 'CONTROL')::bigint AS control_actions,
        MIN(assigned_at) AS first_assigned_at,
        MAX(assigned_at) AS last_assigned_at
    FROM long_outcomes
    GROUP BY
        experiment_id, experiment_name, experiment_status,
        policy_id, policy_version, primary_outcome, causal_estimand, outcome_name
)
SELECT
    g.*,
    CASE
        WHEN g.treatment_matured = 0 OR g.control_matured = 0 THEN NULL
        ELSE (g.treatment_rate - g.control_rate) * 100.0
    END AS itt_difference_pp,
    CASE
        WHEN g.treatment_matured = 0 OR g.control_matured = 0 OR g.control_rate = 0 THEN NULL
        ELSE (g.treatment_rate / g.control_rate) - 1.0
    END AS relative_lift,
    CASE
        WHEN g.treatment_assigned = 0 THEN NULL
        ELSE g.treatment_matured::double precision / g.treatment_assigned::double precision
    END AS treatment_maturity_rate,
    CASE
        WHEN g.control_assigned = 0 THEN NULL
        ELSE g.control_matured::double precision / g.control_assigned::double precision
    END AS control_maturity_rate,
    CASE
        WHEN g.treatment_assigned = 0 THEN NULL
        ELSE g.treatment_actions::double precision / g.treatment_assigned::double precision
    END AS treatment_action_rate,
    CASE
        WHEN g.control_recommendations > 0 OR g.control_actions > 0 THEN true
        ELSE false
    END AS control_contamination_flag,
    CASE
        WHEN g.treatment_assigned = 0 OR g.control_assigned = 0 THEN 'NO_COMPARISON_GROUP'
        WHEN g.treatment_matured = 0 OR g.control_matured = 0 THEN 'WAITING_MATURITY'
        WHEN g.control_recommendations > 0 OR g.control_actions > 0 THEN 'CONTROL_CONTAMINATION'
        ELSE 'READY_FOR_ITT_REVIEW'
    END AS experiment_evidence_status
FROM grouped g;

COMMENT ON VIEW analytics.v_pbi_experiment_performance IS
'Power BI experiment view at experiment x outcome grain. Exposes treatment/control maturity, rates, ITT difference, lift and contamination status.';

-- ============================================================================
-- BLOCK 07. Advisor execution
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_advisor_execution AS
SELECT
    j.recommendation_date,
    j.policy_id,
    j.experiment_id,
    j.codigo_proyecto,
    COALESCE(j.asesor, j.action_owner_proposed, 'SIN_ASESOR') AS asesor,
    j.priority_band,
    COUNT(*)::bigint AS recommendations,
    COUNT(*) FILTER (WHERE j.action_adopted)::bigint AS actions_recorded,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE COUNT(*) FILTER (WHERE j.action_adopted)::double precision / COUNT(*)::double precision
    END AS adoption_rate,
    COUNT(*) FILTER (WHERE j.within_sla IS TRUE)::bigint AS within_sla_n,
    CASE
        WHEN COUNT(*) FILTER (WHERE j.action_adopted) = 0 THEN NULL
        ELSE COUNT(*) FILTER (WHERE j.within_sla IS TRUE)::double precision
             / COUNT(*) FILTER (WHERE j.action_adopted)::double precision
    END AS within_sla_rate,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY j.minutes_to_action)
        FILTER (WHERE j.action_adopted) AS median_minutes_to_action,
    AVG(j.priority_score) AS avg_priority_score,
    AVG(j.p_minuta_60d) AS avg_predicted_minuta,
    COUNT(*) FILTER (WHERE j.separacion_matured)::bigint AS sep_matured,
    AVG(j.separacion_14d) FILTER (WHERE j.separacion_matured) AS sep_rate,
    COUNT(*) FILTER (WHERE j.minuta_matured)::bigint AS minuta_matured,
    AVG(j.minuta_60d) FILTER (WHERE j.minuta_matured) AS minuta_rate,
    COALESCE(SUM(j.total_action_cost),0)::numeric(18,4) AS total_action_cost
FROM analytics.v_pbi_policy_journey j
GROUP BY
    j.recommendation_date, j.policy_id, j.experiment_id,
    j.codigo_proyecto,
    COALESCE(j.asesor, j.action_owner_proposed, 'SIN_ASESOR'),
    j.priority_band;

COMMENT ON VIEW analytics.v_pbi_advisor_execution IS
'Power BI commercial execution fact by date, advisor, project and priority band.';

-- ============================================================================
-- BLOCK 08. Model monitoring
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_model_monitoring AS
WITH base AS (
    SELECT
        date_trunc('week', s.scored_at)::date AS score_week,
        s.model_run_id,
        mr.model_name,
        mr.model_version,
        mr.status AS model_status,
        s.is_provisional,
        e.codigo_proyecto,
        s.priority_band,
        s.priority_score,
        s.p_separacion_14d,
        s.p_minuta_60d,
        e.separacion_14d,
        e.minuta_60d,
        EXISTS (
            SELECT 1
            FROM model_control.model_aliases a
            WHERE a.model_run_id = s.model_run_id
              AND a.decision_system = mr.decision_system
              AND a.model_name = mr.model_name
              AND a.alias_name = 'serving'
        ) AS is_serving
    FROM decision_intelligence.lead_scores s
    JOIN features.lead_evidence e USING (evidence_key)
    JOIN model_control.model_runs mr
      ON mr.model_run_id = s.model_run_id
    WHERE mr.decision_system = 'priorizacion_leads'
)
SELECT
    score_week,
    model_run_id::text AS model_run_id,
    model_name,
    model_version,
    model_status,
    is_provisional,
    is_serving,
    codigo_proyecto,
    priority_band,
    COUNT(*)::bigint AS scores,
    AVG(priority_score) AS avg_priority_score,
    percentile_cont(0.10) WITHIN GROUP (ORDER BY priority_score) AS score_p10,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY priority_score) AS score_p50,
    percentile_cont(0.90) WITHIN GROUP (ORDER BY priority_score) AS score_p90,
    AVG(p_separacion_14d) AS avg_predicted_sep,
    AVG(p_minuta_60d) AS avg_predicted_minuta,
    COUNT(separacion_14d)::bigint AS sep_matured,
    AVG(separacion_14d::double precision) AS actual_sep_rate,
    CASE
        WHEN COUNT(separacion_14d) = 0 THEN NULL
        ELSE (AVG(separacion_14d::double precision) - AVG(p_separacion_14d)) * 100.0
    END AS sep_calibration_gap_pp,
    COUNT(minuta_60d)::bigint AS minuta_matured,
    AVG(minuta_60d::double precision) AS actual_minuta_rate,
    CASE
        WHEN COUNT(minuta_60d) = 0 THEN NULL
        ELSE (AVG(minuta_60d::double precision) - AVG(p_minuta_60d)) * 100.0
    END AS minuta_calibration_gap_pp
FROM base
GROUP BY
    score_week, model_run_id, model_name, model_version,
    model_status, is_provisional, is_serving, codigo_proyecto, priority_band;

COMMENT ON VIEW analytics.v_pbi_model_monitoring IS
'Power BI weekly model monitoring by model version, project and priority band. Includes score distribution and matured calibration gaps.';

-- ============================================================================
-- BLOCK 09. Economic value / causal-value readiness
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_economic_value AS
WITH assignment_outcomes AS (
    SELECT
        e.experiment_id::text AS experiment_id,
        e.experiment_name,
        e.status AS experiment_status,
        COALESCE(NULLIF(e.design_json->>'policy_id',''), 'legacy_unversioned') AS policy_id,
        NULLIF(e.design_json->>'policy_version','') AS policy_version,
        e.primary_outcome,
        a.entity_id AS evidence_key,
        a.treatment_group,
        o.outcome_value,
        o.realized_value
    FROM experiments.assignments a
    JOIN experiments.experiments e
      ON e.experiment_id = a.experiment_id
    LEFT JOIN decision_intelligence.outcomes o
      ON o.decision_system = e.decision_system
     AND o.entity_id = a.entity_id
     AND o.outcome_name = e.primary_outcome
    WHERE e.decision_system = 'priorizacion_leads'
),
groups AS (
    SELECT
        experiment_id,
        experiment_name,
        experiment_status,
        policy_id,
        policy_version,
        primary_outcome,
        treatment_group,
        COUNT(*)::bigint AS assigned_n,
        COUNT(outcome_value)::bigint AS matured_n,
        AVG(outcome_value) AS outcome_rate,
        COUNT(realized_value)::bigint AS realized_value_n,
        AVG(realized_value) AS avg_realized_value,
        COALESCE(SUM(realized_value),0)::numeric(18,4) AS observed_realized_value
    FROM assignment_outcomes
    GROUP BY
        experiment_id, experiment_name, experiment_status,
        policy_id, policy_version, primary_outcome, treatment_group
),
action_costs AS (
    SELECT
        r.context_json->>'experiment_id' AS experiment_id,
        COALESCE(SUM(a.action_cost),0)::numeric(18,4) AS treatment_action_cost
    FROM decision_intelligence.recommendations r
    JOIN decision_intelligence.actions a
      ON a.recommendation_id = r.recommendation_id
    WHERE r.decision_system = 'priorizacion_leads'
      AND NULLIF(r.context_json->>'experiment_id','') IS NOT NULL
    GROUP BY r.context_json->>'experiment_id'
),
pivoted AS (
    SELECT
        g.experiment_id,
        MAX(g.experiment_name) AS experiment_name,
        MAX(g.experiment_status) AS experiment_status,
        MAX(g.policy_id) AS policy_id,
        MAX(g.policy_version) AS policy_version,
        MAX(g.primary_outcome) AS primary_outcome,
        MAX(g.assigned_n) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_assigned,
        MAX(g.assigned_n) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_assigned,
        MAX(g.matured_n) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_matured,
        MAX(g.matured_n) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_matured,
        MAX(g.outcome_rate) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_rate,
        MAX(g.outcome_rate) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_rate,
        MAX(g.realized_value_n) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_realized_value_n,
        MAX(g.realized_value_n) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_realized_value_n,
        MAX(g.avg_realized_value) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_avg_realized_value,
        MAX(g.avg_realized_value) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_avg_realized_value,
        MAX(g.observed_realized_value) FILTER (WHERE g.treatment_group = 'TREATMENT') AS treatment_observed_realized_value,
        MAX(g.observed_realized_value) FILTER (WHERE g.treatment_group = 'CONTROL') AS control_observed_realized_value
    FROM groups g
    GROUP BY g.experiment_id
)
SELECT
    p.*,
    COALESCE(ac.treatment_action_cost,0)::numeric(18,4) AS treatment_action_cost,
    CASE
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0 THEN NULL
        ELSE (p.treatment_rate - p.control_rate) * 100.0
    END AS itt_primary_outcome_pp,
    CASE
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0 THEN NULL
        ELSE (p.treatment_rate - p.control_rate) * p.treatment_matured::double precision
    END AS estimated_incremental_primary_outcomes_on_matured_treatment,
    CASE
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0 THEN NULL
        WHEN p.treatment_realized_value_n <> p.treatment_matured THEN NULL
        WHEN p.control_realized_value_n <> p.control_matured THEN NULL
        ELSE
            (p.treatment_avg_realized_value - p.control_avg_realized_value)
            * p.treatment_matured::numeric
    END AS estimated_incremental_realized_value,
    CASE
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0 THEN NULL
        WHEN p.treatment_realized_value_n <> p.treatment_matured THEN NULL
        WHEN p.control_realized_value_n <> p.control_matured THEN NULL
        ELSE
            (
                (p.treatment_avg_realized_value - p.control_avg_realized_value)
                * p.treatment_matured::numeric
            ) - COALESCE(ac.treatment_action_cost,0)
    END AS estimated_net_incremental_value,
    CASE
        WHEN COALESCE(ac.treatment_action_cost,0) <= 0 THEN NULL
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0 THEN NULL
        WHEN p.treatment_realized_value_n <> p.treatment_matured THEN NULL
        WHEN p.control_realized_value_n <> p.control_matured THEN NULL
        ELSE
            (
                (
                    (p.treatment_avg_realized_value - p.control_avg_realized_value)
                    * p.treatment_matured::numeric
                ) - COALESCE(ac.treatment_action_cost,0)
            ) / ac.treatment_action_cost
    END AS estimated_incremental_roi,
    CASE
        WHEN COALESCE(p.treatment_assigned,0) = 0 OR COALESCE(p.control_assigned,0) = 0
            THEN 'WAITING_COMPARISON_GROUP'
        WHEN COALESCE(p.treatment_matured,0) = 0 OR COALESCE(p.control_matured,0) = 0
            THEN 'WAITING_OUTCOME_MATURITY'
        WHEN p.treatment_realized_value_n <> p.treatment_matured
          OR p.control_realized_value_n <> p.control_matured
            THEN 'WAITING_REALIZED_VALUE'
        ELSE 'READY_FOR_ECONOMIC_ITT_REVIEW'
    END AS economic_value_status
FROM pivoted p
LEFT JOIN action_costs ac
  ON ac.experiment_id = p.experiment_id;

COMMENT ON VIEW analytics.v_pbi_economic_value IS
'Power BI economic-value readiness. Incremental value/ROI remain NULL until treatment/control outcomes and realized_value are complete.';

-- ============================================================================
-- BLOCK 10. Executive command-center row
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_di_executive AS
WITH evidence AS (
    SELECT
        COUNT(*)::bigint AS evidence_n,
        COUNT(*) FILTER (WHERE evidence_source = 'LIVE')::bigint AS live_evidence_n
    FROM features.lead_evidence
),
scores AS (
    SELECT COUNT(*)::bigint AS scores_n
    FROM decision_intelligence.lead_scores
),
serving AS (
    SELECT DISTINCT ON (s.evidence_key)
        s.evidence_key,
        s.model_run_id,
        s.priority_band,
        s.priority_score,
        s.scored_at,
        e.decision_at,
        e.evidence_source,
        e.label_status
    FROM decision_intelligence.lead_scores s
    JOIN features.lead_evidence e USING (evidence_key)
    JOIN model_control.model_runs mr
      ON mr.model_run_id = s.model_run_id
    JOIN model_control.model_aliases a
      ON a.model_run_id = s.model_run_id
     AND a.decision_system = mr.decision_system
     AND a.model_name = mr.model_name
     AND a.alias_name = 'serving'
    WHERE mr.decision_system = 'priorizacion_leads'
    ORDER BY s.evidence_key, s.scored_at DESC
),
serving_counts AS (
    SELECT
        COUNT(*)::bigint AS serving_scores_n,
        COUNT(*) FILTER (
            WHERE evidence_source = 'LIVE'
              AND label_status = 'PENDING'
              AND priority_band IN ('A','B')
              AND decision_at >= CURRENT_TIMESTAMP - interval '7 days'
        )::bigint AS eligible_current_n
    FROM serving
),
latest_serving_model AS (
    SELECT
        mr.model_run_id::text AS model_run_id,
        mr.model_version,
        mr.status AS model_status
    FROM model_control.model_aliases a
    JOIN model_control.model_runs mr
      ON mr.model_run_id = a.model_run_id
    WHERE a.decision_system = 'priorizacion_leads'
      AND a.alias_name = 'serving'
    ORDER BY a.updated_at DESC
    LIMIT 1
),
assignments AS (
    SELECT
        COUNT(*)::bigint AS assigned_n,
        COUNT(*) FILTER (WHERE a.treatment_group = 'TREATMENT')::bigint AS treatment_n,
        COUNT(*) FILTER (WHERE a.treatment_group = 'CONTROL')::bigint AS control_n
    FROM experiments.assignments a
    JOIN experiments.experiments e
      ON e.experiment_id = a.experiment_id
    WHERE e.decision_system = 'priorizacion_leads'
      AND e.design_json->>'policy_id' = 'lead_priority_v2'
),
journey AS (
    SELECT *
    FROM analytics.v_pbi_policy_journey
    WHERE policy_id = 'lead_priority_v2'
),
journey_counts AS (
    SELECT
        COUNT(*)::bigint AS recommendations_n,
        COUNT(*) FILTER (WHERE action_adopted)::bigint AS actions_n,
        COUNT(*) FILTER (WHERE separacion_matured)::bigint AS sep_matured,
        AVG(separacion_14d) FILTER (WHERE separacion_matured) AS sep_rate,
        COUNT(*) FILTER (WHERE minuta_matured)::bigint AS minuta_matured,
        AVG(minuta_60d) FILTER (WHERE minuta_matured) AS minuta_rate,
        CASE
            WHEN COUNT(*) = 0 THEN NULL
            ELSE COUNT(*) FILTER (WHERE action_adopted)::double precision / COUNT(*)::double precision
        END AS adoption_rate,
        CASE
            WHEN COUNT(*) FILTER (WHERE action_adopted) = 0 THEN NULL
            ELSE COUNT(*) FILTER (WHERE within_sla IS TRUE)::double precision
                 / COUNT(*) FILTER (WHERE action_adopted)::double precision
        END AS within_sla_rate,
        COALESCE(SUM(total_action_cost),0)::numeric(18,4) AS total_action_cost
    FROM journey
),
primary_experiment AS (
    SELECT ep.*
    FROM analytics.v_pbi_experiment_performance ep
    WHERE ep.policy_id = 'lead_priority_v2'
      AND ep.outcome_name = ep.primary_outcome
    ORDER BY ep.last_assigned_at DESC NULLS LAST
    LIMIT 1
),
all_counts AS (
    SELECT
        (SELECT COUNT(*)::bigint FROM decision_intelligence.recommendations WHERE decision_system='priorizacion_leads') AS all_recommendations_n,
        (SELECT COUNT(*)::bigint FROM decision_intelligence.actions WHERE decision_system='priorizacion_leads') AS all_actions_n,
        (SELECT COUNT(*)::bigint FROM decision_intelligence.outcomes WHERE decision_system='priorizacion_leads') AS all_outcomes_n
)
SELECT
    CURRENT_TIMESTAMP AS as_of_ts,
    CURRENT_DATE AS as_of_date,
    'priorizacion_leads'::text AS decision_system,
    'lead_priority_v2'::text AS policy_id,
    ev.evidence_n,
    ev.live_evidence_n,
    sc.scores_n,
    svc.serving_scores_n,
    svc.eligible_current_n,
    COALESCE(a.assigned_n,0)::bigint AS assigned_n,
    COALESCE(a.treatment_n,0)::bigint AS treatment_n,
    COALESCE(a.control_n,0)::bigint AS control_n,
    COALESCE(jc.recommendations_n,0)::bigint AS recommendations_n,
    COALESCE(jc.actions_n,0)::bigint AS actions_n,
    jc.adoption_rate,
    jc.within_sla_rate,
    COALESCE(jc.sep_matured,0)::bigint AS sep_matured,
    jc.sep_rate,
    COALESCE(jc.minuta_matured,0)::bigint AS minuta_matured,
    jc.minuta_rate,
    jc.total_action_cost,
    ac.all_recommendations_n,
    ac.all_actions_n,
    ac.all_outcomes_n,
    lm.model_run_id AS serving_model_run_id,
    lm.model_version AS serving_model_version,
    lm.model_status AS serving_model_status,
    pe.experiment_id AS latest_experiment_id,
    pe.experiment_name AS latest_experiment_name,
    pe.experiment_status AS latest_experiment_status,
    pe.itt_difference_pp AS primary_outcome_itt_pp,
    pe.experiment_evidence_status,
    CASE
        WHEN svc.serving_scores_n = 0 THEN 'SCORING'
        WHEN svc.eligible_current_n = 0 THEN 'POLICY_ELIGIBILITY'
        WHEN COALESCE(a.assigned_n,0) = 0 THEN 'EXPERIMENT_ASSIGNMENT'
        WHEN COALESCE(jc.recommendations_n,0) = 0 THEN 'RECOMMENDATION'
        WHEN COALESCE(jc.actions_n,0) = 0 THEN 'ADOPTION'
        WHEN COALESCE(jc.minuta_matured,0) = 0 THEN 'MEASUREMENT'
        WHEN pe.experiment_evidence_status IS NULL OR pe.experiment_evidence_status <> 'READY_FOR_ITT_REVIEW'
            THEN 'EXPERIMENTAL_VALIDATION'
        ELSE 'LEARNING'
    END AS next_bottleneck,
    CASE
        WHEN svc.serving_scores_n > 0
         AND COALESCE(a.assigned_n,0) > 0
         AND COALESCE(jc.recommendations_n,0) > 0
         AND COALESCE(jc.actions_n,0) > 0
         AND (COALESCE(jc.sep_matured,0) > 0 OR COALESCE(jc.minuta_matured,0) > 0)
            THEN true
        ELSE false
    END AS operational_closed_loop,
    CASE
        WHEN pe.experiment_evidence_status = 'READY_FOR_ITT_REVIEW' THEN true
        ELSE false
    END AS experimental_closed_loop
FROM evidence ev
CROSS JOIN scores sc
CROSS JOIN serving_counts svc
CROSS JOIN assignments a
CROSS JOIN journey_counts jc
CROSS JOIN all_counts ac
LEFT JOIN latest_serving_model lm ON true
LEFT JOIN primary_experiment pe ON true;

COMMENT ON VIEW analytics.v_pbi_di_executive IS
'Single-row Power BI executive command center for lead_priority_v2: evidence, serving scores, eligibility, assignments, recommendations, adoption, SLA, outcomes, experiment status and next bottleneck.';

-- ============================================================================
-- BLOCK 11. Small catalog for Power BI discovery / governance
-- ============================================================================

CREATE OR REPLACE VIEW analytics.v_pbi_di_catalog AS
SELECT *
FROM (VALUES
    (1,'analytics.v_pbi_di_executive','EXECUTIVE','1 row','Home: KPI + next bottleneck + closed-loop state'),
    (2,'analytics.v_pbi_policy_funnel','FUNNEL','stage','Default V2 funnel; parameterized function available'),
    (3,'analytics.v_pbi_policy_capacity','POLICY','date x experiment x project x band','Capacity and treatment/control allocation'),
    (4,'analytics.v_pbi_policy_adoption','ADOPTION','date x policy x advisor x band','Recommendation adoption, SLA and observed outcomes'),
    (5,'analytics.v_pbi_experiment_performance','EXPERIMENT','experiment x outcome','Treatment/control, maturity, ITT and contamination'),
    (6,'analytics.v_pbi_advisor_execution','COMMERCIAL','date x advisor x project x band','Commercial execution by advisor'),
    (7,'analytics.v_pbi_model_monitoring','MODEL','week x model x project x band','Score distribution, actuals and calibration'),
    (8,'analytics.v_pbi_economic_value','VALUE','experiment','Economic-value readiness and guarded incremental estimates'),
    (9,'analytics.v_pbi_policy_journey','DETAIL','recommendation','Recommendation-grain lineage for drillthrough')
) AS x(display_order,object_name,layer,grain,purpose);

COMMENT ON VIEW analytics.v_pbi_di_catalog IS
'Catalog of Decision Intelligence Power BI presentation objects and their intended grain.';

COMMIT;
