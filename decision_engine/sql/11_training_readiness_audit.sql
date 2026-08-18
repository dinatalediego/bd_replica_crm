-- Readiness audit for the governed point-in-time separation fall-risk dataset.
--
-- This layer does not change labels or model features. It explains selection
-- into the historical risk set so we do not mistake expected landmark
-- exclusions for data-quality failures, and so class-dependent coverage is
-- visible before any ML benchmark is trained.

CREATE SCHEMA IF NOT EXISTS features;

DROP VIEW IF EXISTS features.v_separation_fall_training_landmark_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_period_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_readiness;

CREATE VIEW features.v_separation_fall_training_readiness AS
WITH source_lifecycles AS (
    SELECT
        separation_id,
        training_target_fall_before_conversion AS target,
        fecha_separacion,
        outcome_at
    FROM decision_intelligence.v_separation_fall_training_outcome
    WHERE training_label_eligible
      AND training_target_fall_before_conversion IS NOT NULL
      AND fecha_separacion IS NOT NULL
      AND outcome_at IS NOT NULL
),
represented AS (
    SELECT DISTINCT
        separation_id,
        target_fall_before_conversion AS target
    FROM features.separation_fall_training_point_in_time
),
audit_counts AS (
    SELECT
        COUNT(*)::bigint AS audit_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'ELIGIBLE'
        )::bigint AS eligible_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'EXCLUDED_OUTCOME_ALREADY_KNOWN_AT_SNAPSHOT'
        )::bigint AS outcome_already_known_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
        )::bigint AS proforma_not_yet_observed_rows,
        COUNT(DISTINCT separation_id) FILTER (
            WHERE snapshot_eligibility_status = 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
        )::bigint AS lifecycles_with_pre_observation_landmarks,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS_AT_SNAPSHOT'
        )::bigint AS proforma_older_than_3_months_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'EXCLUDED_ENTREGA_ALREADY_STARTED_AT_SNAPSHOT'
        )::bigint AS entrega_already_started_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'EXCLUDED_DATED_PAYMENT_ALREADY_KNOWN_AT_SNAPSHOT'
        )::bigint AS dated_payment_already_known_rows,
        COUNT(*) FILTER (
            WHERE snapshot_eligibility_status = 'BLOCKED_MISSING_PROFORMA_FIRST_SEEN_AT'
        )::bigint AS missing_proforma_first_seen_rows,
        MAX(
            CASE
                WHEN snapshot_eligibility_status = 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
                THEN proforma_first_seen_at::date - snapshot_at
            END
        )::integer AS max_days_until_proforma_observed,
        ROUND(
            (
                percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY (proforma_first_seen_at::date - snapshot_at)
                ) FILTER (
                    WHERE snapshot_eligibility_status = 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
                )
            )::numeric,
            2
        ) AS median_days_until_proforma_observed
    FROM features.v_separation_fall_training_point_in_time_audit
),
source_counts AS (
    SELECT
        COUNT(*)::bigint AS source_trainable_lifecycles,
        COUNT(*) FILTER (WHERE target = 1)::bigint AS source_fall_lifecycles,
        COUNT(*) FILTER (WHERE target = 0)::bigint AS source_conversion_lifecycles,
        COUNT(*) FILTER (
            WHERE outcome_at::date = fecha_separacion::date
        )::bigint AS source_same_day_outcomes,
        COUNT(*) FILTER (
            WHERE target = 1 AND outcome_at::date = fecha_separacion::date
        )::bigint AS source_same_day_falls,
        COUNT(*) FILTER (
            WHERE target = 0 AND outcome_at::date = fecha_separacion::date
        )::bigint AS source_same_day_conversions,
        COUNT(*) FILTER (
            WHERE outcome_at::date <= fecha_separacion::date + 7
        )::bigint AS source_outcomes_within_7d,
        COUNT(*) FILTER (
            WHERE target = 1 AND outcome_at::date <= fecha_separacion::date + 7
        )::bigint AS source_falls_within_7d,
        COUNT(*) FILTER (
            WHERE target = 0 AND outcome_at::date <= fecha_separacion::date + 7
        )::bigint AS source_conversions_within_7d
    FROM source_lifecycles
),
represented_counts AS (
    SELECT
        COUNT(*)::bigint AS represented_lifecycles,
        COUNT(*) FILTER (WHERE target = 1)::bigint AS represented_fall_lifecycles,
        COUNT(*) FILTER (WHERE target = 0)::bigint AS represented_conversion_lifecycles
    FROM represented
),
snapshot_counts AS (
    SELECT
        COUNT(*)::bigint AS snapshot_rows,
        COUNT(*) FILTER (WHERE target_fall_before_conversion = 1)::bigint AS fall_snapshot_rows,
        COUNT(*) FILTER (WHERE target_fall_before_conversion = 0)::bigint AS conversion_snapshot_rows
    FROM features.separation_fall_training_point_in_time
)
SELECT
    s.source_trainable_lifecycles,
    s.source_fall_lifecycles,
    s.source_conversion_lifecycles,
    r.represented_lifecycles,
    r.represented_fall_lifecycles,
    r.represented_conversion_lifecycles,
    ROUND(r.represented_lifecycles::numeric / NULLIF(s.source_trainable_lifecycles, 0), 4)
        AS represented_lifecycle_coverage,
    ROUND(r.represented_fall_lifecycles::numeric / NULLIF(s.source_fall_lifecycles, 0), 4)
        AS represented_fall_lifecycle_coverage,
    ROUND(r.represented_conversion_lifecycles::numeric / NULLIF(s.source_conversion_lifecycles, 0), 4)
        AS represented_conversion_lifecycle_coverage,
    ROUND(s.source_fall_lifecycles::numeric / NULLIF(s.source_trainable_lifecycles, 0), 4)
        AS source_lifecycle_fall_rate,
    ROUND(r.represented_fall_lifecycles::numeric / NULLIF(r.represented_lifecycles, 0), 4)
        AS represented_lifecycle_fall_rate,
    ROUND(sn.fall_snapshot_rows::numeric / NULLIF(sn.snapshot_rows, 0), 4)
        AS snapshot_fall_rate,
    sn.snapshot_rows,
    sn.fall_snapshot_rows,
    sn.conversion_snapshot_rows,
    s.source_same_day_outcomes,
    s.source_same_day_falls,
    s.source_same_day_conversions,
    s.source_outcomes_within_7d,
    s.source_falls_within_7d,
    s.source_conversions_within_7d,
    a.audit_rows,
    (s.source_trainable_lifecycles * 9)::bigint AS expected_landmark_audit_rows,
    (
        a.audit_rows - (s.source_trainable_lifecycles * 9)
    )::bigint AS landmark_expansion_accounting_gap,
    a.eligible_rows,
    a.outcome_already_known_rows,
    a.proforma_not_yet_observed_rows,
    a.lifecycles_with_pre_observation_landmarks,
    a.median_days_until_proforma_observed,
    a.max_days_until_proforma_observed,
    a.proforma_older_than_3_months_rows,
    a.entrega_already_started_rows,
    a.dated_payment_already_known_rows,
    a.missing_proforma_first_seen_rows,
    (
        a.audit_rows
        - a.eligible_rows
        - a.outcome_already_known_rows
        - a.proforma_not_yet_observed_rows
        - a.proforma_older_than_3_months_rows
        - a.entrega_already_started_rows
        - a.dated_payment_already_known_rows
        - a.missing_proforma_first_seen_rows
    )::bigint AS eligibility_bucket_accounting_gap,
    'CONDITIONAL_RISK_AMONG_OPPORTUNITIES_STILL_ELIGIBLE_AT_SNAPSHOT'::text
        AS modeling_estimand,
    'DO_NOT_COMPARE_SNAPSHOT_PREVALENCE_DIRECTLY_TO_ALL_SEPARATIONS'::text
        AS prevalence_interpretation
FROM source_counts s
CROSS JOIN represented_counts r
CROSS JOIN snapshot_counts sn
CROSS JOIN audit_counts a;

CREATE VIEW features.v_separation_fall_training_period_profile AS
SELECT
    date_trunc('month', snapshot_at)::date AS snapshot_month,
    COUNT(*)::bigint AS snapshot_rows,
    COUNT(DISTINCT separation_id)::bigint AS distinct_lifecycles,
    COUNT(DISTINCT separation_id) FILTER (
        WHERE target_fall_before_conversion = 1
    )::bigint AS fall_lifecycles,
    COUNT(DISTINCT separation_id) FILTER (
        WHERE target_fall_before_conversion = 0
    )::bigint AS conversion_lifecycles,
    ROUND(
        COUNT(*) FILTER (WHERE target_fall_before_conversion = 1)::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS snapshot_fall_rate
FROM features.separation_fall_training_point_in_time
GROUP BY 1
ORDER BY 1;

CREATE VIEW features.v_separation_fall_training_landmark_profile AS
SELECT
    landmark_day,
    COUNT(*)::bigint AS snapshot_rows,
    COUNT(DISTINCT separation_id)::bigint AS distinct_lifecycles,
    COUNT(DISTINCT separation_id) FILTER (
        WHERE target_fall_before_conversion = 1
    )::bigint AS fall_lifecycles,
    COUNT(DISTINCT separation_id) FILTER (
        WHERE target_fall_before_conversion = 0
    )::bigint AS conversion_lifecycles,
    ROUND(
        COUNT(*) FILTER (WHERE target_fall_before_conversion = 1)::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS snapshot_fall_rate
FROM features.separation_fall_training_point_in_time
GROUP BY landmark_day
ORDER BY landmark_day;

COMMENT ON VIEW features.v_separation_fall_training_readiness IS
'Pre-model readiness audit explaining lifecycle representation, class-dependent risk-set coverage, fast outcomes, landmark accounting, and expected point-in-time exclusions.';

COMMENT ON VIEW features.v_separation_fall_training_period_profile IS
'Monthly point-in-time training coverage/profile for concept-drift and out-of-time split design.';

COMMENT ON VIEW features.v_separation_fall_training_landmark_profile IS
'Landmark-day risk-set profile showing how sample size and conditional fall prevalence evolve as opportunities remain open.';
