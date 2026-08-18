-- Production-oriented fixed-horizon training target for separation_fall_risk.
--
-- Why this exists:
-- * the earlier point-in-time dataset targets eventual FALL vs CONVERTED and is
--   useful for risk-set research, but recent open opportunities are censored;
-- * the operational question is nearer-term: among opportunities that are still
--   eligible at snapshot_at, will a commercial fall occur within the next 30 days?
-- * a fixed horizon lets mature open cases become valid no-fall examples once
--   30 days of follow-up are observable, instead of requiring an eventual sale;
-- * department transfers are competing events, never positive FALL labels;
-- * post-outcome reason fields remain forbidden as features.
--
-- Conservative temporal rule for payment evidence:
-- * dated initial-payment evidence is applied at its actual date;
-- * undated marker/amount evidence has no certified historical first-known time,
--   therefore those lifecycle rows are excluded from this v1 horizon dataset.

CREATE SCHEMA IF NOT EXISTS features;

DROP VIEW IF EXISTS features.v_separation_fall_training_30d_regime_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_30d_health;
DROP VIEW IF EXISTS features.separation_fall_training_30d;
DROP VIEW IF EXISTS features.v_separation_fall_training_30d_audit;

CREATE VIEW features.v_separation_fall_training_30d_audit AS
WITH landmarks(day_n) AS (
    VALUES
        (0::integer),
        (7::integer),
        (14::integer),
        (21::integer),
        (30::integer),
        (45::integer),
        (60::integer),
        (75::integer),
        (90::integer)
),
observation_cutoff AS (
    SELECT MAX(observed_at)::date AS observed_through
    FROM (
        SELECT MAX(COALESCE(p.fecha_fin, p.fecha_inicio)) AS observed_at
        FROM raw_cygnus.procesos p
        UNION ALL
        SELECT MAX(c.analytics_refreshed_at) AS observed_at
        FROM core.fact_ciclo_comercial_unidad c
    ) x
),
proforma_recency AS (
    SELECT
        codigo_proforma::text AS codigo_proforma,
        MIN(fecha_creacion) AS proforma_first_seen_at
    FROM raw_cygnus.proforma_unidad
    WHERE codigo_proforma IS NOT NULL
    GROUP BY codigo_proforma::text
),
base AS (
    SELECT
        t.separation_id,
        t.codigo_proforma,
        t.codigo_unidad,
        t.codigo_proyecto,
        t.documento_cliente,
        t.asesor,
        t.tipo_unidad_principal,
        t.fecha_separacion,
        t.outcome_at,
        t.training_outcome_class,
        t.fecha_pago_ci,
        t.pago_ci_marker_confirmado,
        t.monto_pago_ci_positivo,
        t.evidencia_pago_ci_confirmada,
        pr.proforma_first_seen_at,
        CASE
            WHEN t.fecha_separacion::date >= DATE '2026-01-01'
                THEN 'POST_2026_PAYMENT_DATE_REGIME'
            ELSE 'PRE_2026_LEGACY_COMPATIBILITY_REGIME'
        END::text AS label_measurement_regime
    FROM decision_intelligence.v_separation_fall_training_outcome t
    LEFT JOIN proforma_recency pr
      ON pr.codigo_proforma = t.codigo_proforma
    WHERE t.fecha_separacion IS NOT NULL
      AND t.training_outcome_class IN (
          'FELL', 'CONVERTED', 'TRANSFER_UNIT', 'CENSORED_OPEN',
          'CONVERSION_EVIDENCE_UNDATED_OR_NOT_IN_LIFECYCLE'
      )
),
expanded AS (
    SELECT
        b.*,
        l.day_n AS landmark_day,
        (b.fecha_separacion::date + l.day_n) AS snapshot_at,
        o.observed_through,
        (b.fecha_separacion::date + l.day_n + 30) AS horizon_end_at
    FROM base b
    CROSS JOIN landmarks l
    CROSS JOIN observation_cutoff o
),
eligibility AS (
    SELECT
        e.*,
        CASE
            WHEN e.observed_through IS NULL
                THEN 'BLOCKED_MISSING_OBSERVATION_CUTOFF'
            WHEN e.snapshot_at > e.observed_through
                THEN 'EXCLUDED_SNAPSHOT_AFTER_OBSERVATION_CUTOFF'
            WHEN e.proforma_first_seen_at IS NULL
                THEN 'BLOCKED_MISSING_PROFORMA_FIRST_SEEN_AT'
            WHEN e.proforma_first_seen_at::date > e.snapshot_at
                THEN 'EXCLUDED_PROFORMA_NOT_YET_OBSERVED_AT_SNAPSHOT'
            WHEN e.proforma_first_seen_at < e.snapshot_at - interval '3 months'
                THEN 'EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS_AT_SNAPSHOT'
            WHEN e.outcome_at IS NOT NULL
             AND e.outcome_at::date <= e.snapshot_at
                THEN 'EXCLUDED_OUTCOME_ALREADY_KNOWN_AT_SNAPSHOT'
            WHEN e.fecha_pago_ci IS NOT NULL
             AND e.fecha_pago_ci::date <= e.snapshot_at
                THEN 'EXCLUDED_DATED_PAYMENT_ALREADY_KNOWN_AT_SNAPSHOT'
            WHEN e.evidencia_pago_ci_confirmada
             AND e.fecha_pago_ci IS NULL
                THEN 'EXCLUDED_UNDATED_PAYMENT_EVIDENCE_TIMING_AMBIGUOUS'
            WHEN EXISTS (
                SELECT 1
                FROM raw_cygnus.procesos p
                WHERE lower(coalesce(p.nombre::text, '')) = 'entrega'
                  AND p.codigo_proforma::text = e.codigo_proforma
                  AND p.codigo_unidad::text = e.codigo_unidad
                  AND p.fecha_inicio IS NOT NULL
                  AND p.fecha_inicio::date <= e.snapshot_at
            )
                THEN 'EXCLUDED_ENTREGA_ALREADY_STARTED_AT_SNAPSHOT'
            ELSE 'ELIGIBLE_FOR_HORIZON_LABEL'
        END::text AS snapshot_eligibility_status
    FROM expanded e
),
labels AS (
    SELECT
        e.*,
        CASE
            WHEN e.snapshot_eligibility_status <> 'ELIGIBLE_FOR_HORIZON_LABEL'
                THEN e.snapshot_eligibility_status
            WHEN e.training_outcome_class = 'TRANSFER_UNIT'
             AND e.outcome_at IS NOT NULL
             AND e.outcome_at::date > e.snapshot_at
             AND e.outcome_at::date <= e.horizon_end_at
                THEN 'EXCLUDED_TRANSFER_COMPETING_EVENT_WITHIN_30D'
            WHEN e.training_outcome_class = 'FELL'
             AND e.outcome_at IS NOT NULL
             AND e.outcome_at::date > e.snapshot_at
             AND e.outcome_at::date <= e.horizon_end_at
                THEN 'LABELED_FALL_WITHIN_30D'
            WHEN e.training_outcome_class = 'CONVERTED'
             AND e.outcome_at IS NOT NULL
             AND e.outcome_at::date > e.snapshot_at
             AND e.outcome_at::date <= e.horizon_end_at
                THEN 'LABELED_NO_FALL_CONVERTED_WITHIN_30D'
            WHEN e.observed_through >= e.horizon_end_at
                THEN 'LABELED_NO_FALL_FULL_30D_FOLLOWUP'
            ELSE 'CENSORED_INCOMPLETE_30D_FOLLOWUP'
        END::text AS horizon_label_status
    FROM eligibility e
)
SELECT
    separation_id,
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    documento_cliente,
    asesor,
    tipo_unidad_principal,
    fecha_separacion,
    proforma_first_seen_at,
    landmark_day,
    snapshot_at,
    horizon_end_at,
    observed_through,
    snapshot_eligibility_status,
    horizon_label_status,
    label_measurement_regime,

    CASE
        WHEN horizon_label_status = 'LABELED_FALL_WITHIN_30D' THEN 1
        WHEN horizon_label_status IN (
            'LABELED_NO_FALL_CONVERTED_WITHIN_30D',
            'LABELED_NO_FALL_FULL_30D_FOLLOWUP'
        ) THEN 0
        ELSE NULL::integer
    END AS target_fall_within_30d,

    -- Structural/temporal v1 features known at snapshot_at.
    landmark_day::integer AS days_since_separation,
    greatest(0, snapshot_at - proforma_first_seen_at::date)::integer
        AS proforma_age_days_at_snapshot,
    greatest(0, fecha_separacion::date - proforma_first_seen_at::date)::integer
        AS proforma_age_days_at_separation,
    extract(isodow from snapshot_at)::integer AS snapshot_iso_weekday,
    extract(month from snapshot_at)::integer AS snapshot_month,

    30::integer AS prediction_horizon_days,
    false::boolean AS interaction_features_certified,
    'STRUCTURAL_TEMPORAL_30D_V1'::text AS feature_scope,
    'GROUP_BY_SEPARATION_ID_OUT_OF_TIME_AND_HORIZON_CENSORING_REQUIRED'::text
        AS evaluation_contract
FROM labels;

CREATE VIEW features.separation_fall_training_30d AS
WITH labeled AS (
    SELECT *
    FROM features.v_separation_fall_training_30d_audit
    WHERE target_fall_within_30d IS NOT NULL
),
weighted AS (
    SELECT
        l.*,
        COUNT(*) OVER (PARTITION BY separation_id) AS snapshots_per_separation
    FROM labeled l
)
SELECT
    separation_id,
    codigo_proforma,
    codigo_unidad,
    codigo_proyecto,
    documento_cliente,
    asesor,
    tipo_unidad_principal,
    fecha_separacion,
    snapshot_at,
    horizon_end_at,
    landmark_day,
    days_since_separation,
    proforma_age_days_at_snapshot,
    proforma_age_days_at_separation,
    snapshot_iso_weekday,
    snapshot_month,
    label_measurement_regime,
    target_fall_within_30d,
    snapshots_per_separation,
    (1.0 / nullif(snapshots_per_separation, 0))::numeric AS lifecycle_balancing_weight,
    prediction_horizon_days,
    feature_scope,
    interaction_features_certified,
    evaluation_contract
FROM weighted;

CREATE VIEW features.v_separation_fall_training_30d_health AS
SELECT
    COUNT(*)::bigint AS labeled_snapshot_rows,
    COUNT(DISTINCT separation_id)::bigint AS labeled_lifecycles,
    COUNT(*) FILTER (WHERE target_fall_within_30d = 1)::bigint AS fall_within_30d_rows,
    COUNT(*) FILTER (WHERE target_fall_within_30d = 0)::bigint AS no_fall_within_30d_rows,
    COUNT(DISTINCT separation_id) FILTER (WHERE target_fall_within_30d = 1)::bigint
        AS lifecycles_with_fall_within_30d,
    ROUND(
        COUNT(*) FILTER (WHERE target_fall_within_30d = 1)::numeric
        / NULLIF(COUNT(*), 0), 4
    ) AS snapshot_fall_within_30d_rate,
    MIN(snapshot_at) AS oldest_snapshot_at,
    MAX(snapshot_at) AS newest_snapshot_at,
    MAX(horizon_end_at) AS latest_horizon_end_at,
    MAX(prediction_horizon_days)::integer AS prediction_horizon_days,
    COUNT(*) FILTER (WHERE snapshots_per_separation <= 0)::bigint AS invalid_snapshot_weight_rows,
    COUNT(*) FILTER (WHERE lifecycle_balancing_weight IS NULL)::bigint AS missing_lifecycle_weight_rows,
    COUNT(*) FILTER (WHERE interaction_features_certified)::bigint
        AS rows_with_certified_interaction_features,
    (
        SELECT MAX(observed_through)
        FROM features.v_separation_fall_training_30d_audit
    ) AS observed_through,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_30d_audit
        WHERE horizon_label_status = 'CENSORED_INCOMPLETE_30D_FOLLOWUP'
    ) AS censored_incomplete_30d_followup,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_30d_audit
        WHERE horizon_label_status = 'EXCLUDED_TRANSFER_COMPETING_EVENT_WITHIN_30D'
    ) AS excluded_transfer_competing_event_within_30d,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_30d_audit
        WHERE horizon_label_status = 'EXCLUDED_UNDATED_PAYMENT_EVIDENCE_TIMING_AMBIGUOUS'
    ) AS excluded_undated_payment_evidence_timing_ambiguous,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_30d_audit
        WHERE horizon_label_status = 'BLOCKED_MISSING_PROFORMA_FIRST_SEEN_AT'
    ) AS blocked_missing_proforma_first_seen,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_30d_audit
        WHERE horizon_label_status = 'BLOCKED_MISSING_OBSERVATION_CUTOFF'
    ) AS blocked_missing_observation_cutoff
FROM features.separation_fall_training_30d;

CREATE VIEW features.v_separation_fall_training_30d_regime_profile AS
SELECT
    label_measurement_regime,
    date_trunc('year', snapshot_at)::date AS snapshot_year,
    COUNT(*)::bigint AS snapshot_rows,
    COUNT(DISTINCT separation_id)::bigint AS distinct_lifecycles,
    COUNT(*) FILTER (WHERE target_fall_within_30d = 1)::bigint AS fall_within_30d_rows,
    COUNT(*) FILTER (WHERE target_fall_within_30d = 0)::bigint AS no_fall_within_30d_rows,
    ROUND(
        COUNT(*) FILTER (WHERE target_fall_within_30d = 1)::numeric
        / NULLIF(COUNT(*), 0), 4
    ) AS fall_within_30d_rate
FROM features.separation_fall_training_30d
GROUP BY 1, 2
ORDER BY 2, 1;

COMMENT ON VIEW features.v_separation_fall_training_30d_audit IS
'30-day point-in-time label audit including open lifecycles, follow-up censoring, competing transfers and conservative exclusion of undated payment evidence.';

COMMENT ON VIEW features.separation_fall_training_30d IS
'Operational 30-day fall-risk training set. Target=fall within 30 days among opportunities eligible at snapshot; grouped out-of-time evaluation required.';

COMMENT ON VIEW features.v_separation_fall_training_30d_health IS
'Readiness and censoring counters for the governed 30-day fall-risk training set.';

COMMENT ON VIEW features.v_separation_fall_training_30d_regime_profile IS
'30-day target profile split by pre-2026 legacy conversion measurement vs post-2026 payment-date regime.';
