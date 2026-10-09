BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS model_control;

-- ===============================================================
-- Medallio Forecast Factory v1.0.3
-- Evidence Calendar + Automated Maturity Evaluator + Model Scoreboard
-- ===============================================================

-- v1.0.2 deliberately allowed monthly intervals to incubate.
-- Therefore canonical evaluation must also permit NULL interval metrics.
ALTER TABLE analytics.forecast_evaluation_v1
    ALTER COLUMN interval_hit DROP NOT NULL,
    ALTER COLUMN interval_width DROP NOT NULL;


-- ---------------------------------------------------------------
-- 1. Automated maturity-cycle ledger
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_control.forecast_maturity_cycle_v103 (
    cycle_id bigserial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,

    cycle_status text NOT NULL DEFAULT 'RUNNING',
    trigger_source text NOT NULL DEFAULT 'MANUAL',

    actual_rows_before integer,
    actual_rows_after integer,

    mature_candidates integer,
    evaluation_rows_before integer,
    evaluation_rows_after integer,

    new_evidence_rows integer,
    latest_actual_period date,
    next_evidence_unlock date,

    message text,
    error_detail text,

    CHECK(cycle_status IN ('RUNNING','OK','ERROR'))
);


-- ---------------------------------------------------------------
-- 2. Human-governed champion registry
--
-- The scoreboard may recommend a challenger.
-- It does NOT automatically declare a champion.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_control.forecast_champion_registry_v103 (
    champion_assignment_id bigserial PRIMARY KEY,

    scope_level text NOT NULL,
    project_key text,

    target_name text NOT NULL DEFAULT 'sales_units',
    lead_time_bucket text NOT NULL,

    model_version_id bigint NOT NULL
        REFERENCES model_control.forecast_model_registry_v1(model_version_id),

    assignment_status text NOT NULL DEFAULT 'APPROVED',
    approved_by text NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),
    approval_note text,

    evidence_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,

    retired_at timestamptz,

    CHECK(scope_level IN ('PORTFOLIO','PROJECT')),
    CHECK(assignment_status IN ('APPROVED','RETIRED')),
    CHECK(
        (scope_level='PORTFOLIO' AND project_key IS NULL)
        OR
        (scope_level='PROJECT' AND project_key IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_forecast_champion_active_v103
ON model_control.forecast_champion_registry_v103(
    scope_level,
    coalesce(project_key,'__PORTFOLIO__'),
    target_name,
    lead_time_bucket
)
WHERE assignment_status='APPROVED';


-- ---------------------------------------------------------------
-- 3. Evaluation sample
--
-- Important statistical guard:
-- many forecast vintages may point at the same model/project/target month.
-- We do not let duplicated vintages inflate the effective sample size.
--
-- Policy: one latest valid issuance within each lead-time bucket:
--
-- model version × project × target period × lead-time bucket × evidence class.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_evaluation_candidate_v103 AS
SELECT *
FROM (
    SELECT
        mc.*,

        -- model_name / model_version / model_family already come from
        -- analytics.v_forecast_monthly_maturity_clock_v102 via mc.*.
        -- Only model_version_id is missing and must be added here.
        r.model_version_id,

        row_number() OVER (
            PARTITION BY
                r.model_version_id,
                mc.project_key,
                mc.target_name,
                mc.segment_key,
                mc.forecast_for_period,
                mc.lead_time_bucket,
                mc.evidence_class
            ORDER BY
                mc.issued_at DESC,
                mc.prediction_id DESC
        ) AS sample_rank

    FROM analytics.v_forecast_monthly_maturity_clock_v102 mc
    JOIN model_control.forecast_run_v1 r
      ON r.run_id=mc.run_id
) ranked
WHERE sample_rank=1;


-- ---------------------------------------------------------------
-- 4. Evidence Calendar detail
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_evidence_calendar_detail_v103 AS
SELECT
    c.prediction_id,
    c.run_id,
    c.model_version_id,
    c.model_name,
    c.model_version,
    c.model_family,

    c.project_key,
    c.target_name,
    c.segment_key,

    c.evidence_class,
    c.lead_time_bucket,
    c.lead_time_days,
    c.lead_time_months,

    c.issued_at,
    c.data_cutoff_date,

    c.forecast_for_period AS target_period,
    c.maturity_date AS expected_evidence_unlock,

    (c.maturity_date - current_date) AS days_to_evidence_unlock,

    c.maturity_status,
    c.compatibility_status,
    c.strict_prospective_order_valid,

    CASE
        WHEN c.maturity_status='MATURE' THEN 'MATURE_READY'
        WHEN c.maturity_status='BLOCKED_SCOPE' THEN 'BLOCKED_SCOPE'
        WHEN c.maturity_date < current_date THEN 'OUTCOME_DUE'
        WHEN c.maturity_date = current_date THEN 'UNLOCK_TODAY'
        ELSE 'INCUBATING'
    END AS calendar_status,

    CASE
        WHEN e.prediction_id IS NOT NULL THEN true
        ELSE false
    END AS evaluated,

    e.evaluated_at

FROM analytics.v_forecast_evaluation_candidate_v103 c
LEFT JOIN analytics.forecast_evaluation_v1 e
  ON e.prediction_id=c.prediction_id;


-- ---------------------------------------------------------------
-- 5. Evidence Calendar summary
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_evidence_calendar_v103 AS
SELECT
    expected_evidence_unlock,
    target_period,
    evidence_class,
    lead_time_bucket,

    count(*) AS evaluation_candidates,
    count(DISTINCT project_key) AS projects,
    count(DISTINCT model_version_id) AS models,

    count(*) FILTER(WHERE calendar_status='INCUBATING') AS incubating_candidates,
    count(*) FILTER(WHERE calendar_status='UNLOCK_TODAY') AS unlock_today_candidates,
    count(*) FILTER(WHERE calendar_status='OUTCOME_DUE') AS outcome_due_candidates,
    count(*) FILTER(WHERE calendar_status='BLOCKED_SCOPE') AS blocked_scope_candidates,
    count(*) FILTER(WHERE calendar_status='MATURE_READY') AS mature_ready_candidates,
    count(*) FILTER(WHERE evaluated) AS evaluated_candidates,

    min(days_to_evidence_unlock) AS days_to_evidence_unlock

FROM analytics.v_forecast_evidence_calendar_detail_v103
GROUP BY
    expected_evidence_unlock,
    target_period,
    evidence_class,
    lead_time_bucket;


-- ---------------------------------------------------------------
-- 6. Current strict prospective evaluation base
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_scoreboard_base_v103 AS
SELECT
    e.evaluation_id,
    e.prediction_id,
    e.actual_id,
    e.evaluated_at,

    c.run_id,
    c.model_version_id,
    c.model_name,
    c.model_version,
    c.model_family,

    c.project_key,
    c.target_name,
    c.segment_key,
    c.forecast_for_period AS target_period,
    c.lead_time_bucket,
    c.lead_time_days,
    c.lead_time_months,

    e.actual_value,
    e.prediction,
    e.naive_prediction,

    e.signed_error,
    e.absolute_error,
    e.ape,

    e.naive_signed_error,
    e.naive_absolute_error,
    e.naive_ape,

    e.interval_hit,
    e.interval_width,

    e.evidence_class,
    e.leakage_safe

FROM analytics.forecast_evaluation_v1 e
JOIN analytics.v_forecast_evaluation_candidate_v103 c
  ON c.prediction_id=e.prediction_id
WHERE
    e.evidence_class='PROSPECTIVE'
    AND e.leakage_safe=true;


-- ---------------------------------------------------------------
-- 7. Portfolio model scoreboard
--
-- Important:
-- model promotion needs temporal breadth, not just many cross-sectional rows
-- from one target month.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_model_scoreboard_portfolio_v103 AS
WITH metrics AS (
    SELECT
        model_version_id,
        model_name,
        model_version,
        model_family,
        target_name,
        lead_time_bucket,

        count(*) AS mature_pairs,
        count(DISTINCT target_period) AS distinct_target_periods,
        count(DISTINCT project_key) AS distinct_projects,

        min(target_period) AS first_target_period,
        max(target_period) AS latest_target_period,

        sum(absolute_error)
            / nullif(sum(abs(actual_value)),0) AS wape,

        sum(signed_error)
            / nullif(sum(abs(actual_value)),0) AS bias,

        sum(naive_absolute_error)
            / nullif(sum(abs(actual_value)),0) AS naive_wape,

        1 - (
            (sum(absolute_error) / nullif(sum(abs(actual_value)),0))
            /
            nullif(
                (sum(naive_absolute_error) / nullif(sum(abs(actual_value)),0)),
                0
            )
        ) AS skill_vs_naive,

        avg(
            CASE
                WHEN interval_hit IS NULL THEN NULL
                WHEN interval_hit THEN 1.0
                ELSE 0.0
            END
        ) AS interval_coverage,

        avg(interval_width) AS avg_interval_width

    FROM analytics.v_forecast_scoreboard_base_v103
    GROUP BY
        model_version_id,
        model_name,
        model_version,
        model_family,
        target_name,
        lead_time_bucket
),
classified AS (
    SELECT
        m.*,

        CASE
            WHEN m.distinct_target_periods < 3
                THEN 'INCUBATING_TIME'
            WHEN m.distinct_projects < 3
                THEN 'INCUBATING_BREADTH'
            WHEN m.mature_pairs < 6
                THEN 'INCUBATING_SAMPLE'
            WHEN m.wape IS NULL OR m.naive_wape IS NULL
                THEN 'BLOCK'
            WHEN m.wape > 0.25
                THEN 'WARN_WAPE'
            WHEN m.skill_vs_naive <= 0.0
                THEN 'WARN_SKILL'
            WHEN abs(m.bias) > 0.15
                THEN 'WARN_BIAS'
            ELSE 'READY_FOR_HUMAN_REVIEW'
        END AS promotion_readiness,

        CASE
            WHEN m.interval_coverage IS NULL
                THEN 'INTERVAL_INCUBATING'
            WHEN m.interval_coverage < 0.60
                THEN 'INTERVAL_WARN'
            ELSE 'INTERVAL_PASS'
        END AS uncertainty_status

    FROM metrics m
)
SELECT *
FROM classified;


-- ---------------------------------------------------------------
-- 8. Project-level model scoreboard
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_model_scoreboard_project_v103 AS
WITH metrics AS (
    SELECT
        model_version_id,
        model_name,
        model_version,
        model_family,

        project_key,
        target_name,
        lead_time_bucket,

        count(*) AS mature_pairs,
        count(DISTINCT target_period) AS distinct_target_periods,

        min(target_period) AS first_target_period,
        max(target_period) AS latest_target_period,

        sum(absolute_error)
            / nullif(sum(abs(actual_value)),0) AS wape,

        sum(signed_error)
            / nullif(sum(abs(actual_value)),0) AS bias,

        sum(naive_absolute_error)
            / nullif(sum(abs(actual_value)),0) AS naive_wape,

        1 - (
            (sum(absolute_error) / nullif(sum(abs(actual_value)),0))
            /
            nullif(
                (sum(naive_absolute_error) / nullif(sum(abs(actual_value)),0)),
                0
            )
        ) AS skill_vs_naive,

        avg(
            CASE
                WHEN interval_hit IS NULL THEN NULL
                WHEN interval_hit THEN 1.0
                ELSE 0.0
            END
        ) AS interval_coverage

    FROM analytics.v_forecast_scoreboard_base_v103
    GROUP BY
        model_version_id,
        model_name,
        model_version,
        model_family,
        project_key,
        target_name,
        lead_time_bucket
)
SELECT
    m.*,

    CASE
        WHEN m.distinct_target_periods < 3
            THEN 'INCUBATING_TIME'
        WHEN m.mature_pairs < 3
            THEN 'INCUBATING_SAMPLE'
        WHEN m.wape IS NULL OR m.naive_wape IS NULL
            THEN 'BLOCK'
        WHEN m.wape > 0.30
            THEN 'WARN_WAPE'
        WHEN m.skill_vs_naive <= 0.0
            THEN 'WARN_SKILL'
        WHEN abs(m.bias) > 0.20
            THEN 'WARN_BIAS'
        ELSE 'READY_FOR_HUMAN_REVIEW'
    END AS promotion_readiness

FROM metrics m;


-- ---------------------------------------------------------------
-- 9. Recommended challenger
--
-- This view recommends; it never promotes.
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_challenger_recommendation_v103 AS
WITH eligible AS (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY s.target_name, s.lead_time_bucket
            ORDER BY
                s.skill_vs_naive DESC NULLS LAST,
                s.wape ASC NULLS LAST,
                abs(s.bias) ASC NULLS LAST,
                s.mature_pairs DESC,
                s.model_name
        ) AS recommendation_rank
    FROM analytics.v_forecast_model_scoreboard_portfolio_v103 s
    WHERE s.promotion_readiness='READY_FOR_HUMAN_REVIEW'
),
approved AS (
    SELECT
        c.target_name,
        c.lead_time_bucket,
        c.model_version_id,
        mr.model_name AS approved_model_name,
        c.approved_by,
        c.approved_at,
        c.approval_note
    FROM model_control.forecast_champion_registry_v103 c
    JOIN model_control.forecast_model_registry_v1 mr
      ON mr.model_version_id=c.model_version_id
    WHERE
        c.scope_level='PORTFOLIO'
        AND c.assignment_status='APPROVED'
)
SELECT
    b.lead_time_bucket,
    'sales_units'::text AS target_name,

    a.model_version_id AS approved_champion_model_version_id,
    a.approved_model_name,
    a.approved_by,
    a.approved_at,

    e.model_version_id AS recommended_model_version_id,
    e.model_name AS recommended_model_name,
    e.wape AS recommended_wape,
    e.bias AS recommended_bias,
    e.naive_wape AS recommended_naive_wape,
    e.skill_vs_naive AS recommended_skill_vs_naive,
    e.mature_pairs AS recommended_mature_pairs,
    e.distinct_target_periods AS recommended_target_periods,
    e.distinct_projects AS recommended_projects,

    CASE
        WHEN a.model_version_id IS NOT NULL
            THEN 'CHAMPION_DECLARED'
        WHEN e.model_version_id IS NOT NULL
            THEN 'READY_FOR_HUMAN_REVIEW'
        ELSE 'NOT_YET_DECLARED'
    END AS champion_status

FROM (
    SELECT DISTINCT lead_time_bucket
    FROM analytics.v_forecast_monthly_current_v102
    WHERE evidence_class='PROSPECTIVE'
) b
LEFT JOIN approved a
  ON a.target_name='sales_units'
 AND a.lead_time_bucket=b.lead_time_bucket
LEFT JOIN eligible e
  ON e.target_name='sales_units'
 AND e.lead_time_bucket=b.lead_time_bucket
 AND e.recommendation_rank=1;


-- ---------------------------------------------------------------
-- 10. CEO predictive evidence status
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_forecast_ceo_evidence_status_v103 AS
WITH raw AS (
    SELECT
        count(*) FILTER(WHERE evidence_class='PROSPECTIVE') AS prospective_predictions,
        count(*) FILTER(WHERE evidence_class='SHADOW') AS shadow_predictions
    FROM analytics.v_forecast_monthly_current_v102
),
candidate AS (
    SELECT
        count(*) FILTER(WHERE evidence_class='PROSPECTIVE') AS prospective_candidates,
        count(*) FILTER(
            WHERE evidence_class='PROSPECTIVE'
              AND maturity_status='MATURE'
        ) AS mature_candidates,
        count(*) FILTER(
            WHERE evidence_class='PROSPECTIVE'
              AND maturity_status='INCUBATING'
        ) AS incubating_candidates
    FROM analytics.v_forecast_evaluation_candidate_v103
),
evaluated AS (
    SELECT count(*) AS evaluated_prospective_pairs
    FROM analytics.v_forecast_scoreboard_base_v103
),
calendar AS (
    SELECT
        min(expected_evidence_unlock)
            FILTER(
                WHERE evidence_class='PROSPECTIVE'
                  AND expected_evidence_unlock >= current_date
            ) AS next_evidence_unlock
    FROM analytics.v_forecast_evidence_calendar_detail_v103
),
next_count AS (
    SELECT count(*) AS expected_pairs_next_unlock
    FROM analytics.v_forecast_evidence_calendar_detail_v103 d
    CROSS JOIN calendar c
    WHERE
        d.evidence_class='PROSPECTIVE'
        AND d.expected_evidence_unlock=c.next_evidence_unlock
),
ready AS (
    SELECT count(*) AS model_cells_ready_for_review
    FROM analytics.v_forecast_model_scoreboard_portfolio_v103
    WHERE promotion_readiness='READY_FOR_HUMAN_REVIEW'
),
champion AS (
    SELECT
        count(*) FILTER(WHERE champion_status='CHAMPION_DECLARED') AS declared_cells,
        count(*) FILTER(WHERE champion_status='READY_FOR_HUMAN_REVIEW') AS review_ready_cells
    FROM analytics.v_forecast_challenger_recommendation_v103
)
SELECT
    r.prospective_predictions,
    r.shadow_predictions,

    c.prospective_candidates,
    c.mature_candidates,
    c.incubating_candidates,

    e.evaluated_prospective_pairs,

    cal.next_evidence_unlock,
    n.expected_pairs_next_unlock,

    ready.model_cells_ready_for_review,

    champion.declared_cells,
    champion.review_ready_cells,

    CASE
        WHEN champion.declared_cells > 0
            THEN 'CHAMPION_DECLARED'
        WHEN champion.review_ready_cells > 0
            THEN 'READY_FOR_HUMAN_REVIEW'
        ELSE 'NOT_YET_DECLARED'
    END AS portfolio_champion_status

FROM raw r
CROSS JOIN candidate c
CROSS JOIN evaluated e
CROSS JOIN calendar cal
CROSS JOIN next_count n
CROSS JOIN ready
CROSS JOIN champion;


-- ---------------------------------------------------------------
-- 11. Power BI surfaces
-- ---------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pbi_forecast_evidence_calendar_v103 AS
SELECT *
FROM analytics.v_forecast_evidence_calendar_v103;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_model_scoreboard_v103 AS
SELECT *
FROM analytics.v_forecast_model_scoreboard_portfolio_v103;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_project_scoreboard_v103 AS
SELECT *
FROM analytics.v_forecast_model_scoreboard_project_v103;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_champion_status_v103 AS
SELECT *
FROM analytics.v_forecast_challenger_recommendation_v103;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_ceo_evidence_status_v103 AS
SELECT *
FROM analytics.v_forecast_ceo_evidence_status_v103;


CREATE OR REPLACE VIEW analytics.v_pbi_forecast_maturity_cycles_v103 AS
SELECT *
FROM model_control.forecast_maturity_cycle_v103;


COMMENT ON VIEW analytics.v_forecast_evaluation_candidate_v103 IS
'One evaluation sample per model/project/target/lead bucket/evidence class; prevents repeated forecast vintages from inflating sample size.';
COMMENT ON VIEW analytics.v_forecast_model_scoreboard_portfolio_v103 IS
'Prospective model scoreboard requiring temporal breadth before human champion review.';
COMMENT ON VIEW analytics.v_forecast_challenger_recommendation_v103 IS
'Recommends a challenger only; champion promotion always requires explicit human approval.';

COMMIT;
