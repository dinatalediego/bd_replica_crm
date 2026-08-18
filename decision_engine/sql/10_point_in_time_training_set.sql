-- Point-in-time supervised training set for separation_fall_risk.
--
-- Purpose:
-- * reproduce the decision problem at historical observation times;
-- * never expose post-outcome fields to the model feature view;
-- * use only rows whose commercial outcome was still unknown at snapshot_at;
-- * align eligibility with the live 3-calendar-month proforma window;
-- * keep transfer outcomes out of binary training;
-- * defer interaction features until a historical interaction contract is certified.
--
-- IMPORTANT: this is a first governed structural/temporal baseline dataset.
-- It is intentionally not the final production feature set.
--
-- RERUN / MIGRATION SAFETY:
-- downstream views introduced by SQL 11 and 12 can already exist on a repeated
-- installation and depend on the point-in-time views rebuilt below. PostgreSQL
-- correctly refuses to drop a referenced view. Tear down only our known
-- downstream Decision Engine views first, in reverse dependency order, rather
-- than using DROP ... CASCADE and risking unrelated objects.

CREATE SCHEMA IF NOT EXISTS features;

-- SQL 12 downstream views.
DROP VIEW IF EXISTS features.v_separation_fall_training_30d_regime_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_30d_health;
DROP VIEW IF EXISTS features.separation_fall_training_30d;
DROP VIEW IF EXISTS features.v_separation_fall_training_30d_audit;

-- SQL 11 downstream views that depend directly on SQL 10.
DROP VIEW IF EXISTS features.v_separation_fall_training_landmark_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_period_profile;
DROP VIEW IF EXISTS features.v_separation_fall_training_readiness;

-- SQL 10 views, now safe to rebuild.
DROP VIEW IF EXISTS features.v_separation_fall_training_point_in_time_health;
DROP VIEW IF EXISTS features.separation_fall_training_point_in_time;
DROP VIEW IF EXISTS features.v_separation_fall_training_point_in_time_audit;

CREATE VIEW features.v_separation_fall_training_point_in_time_audit AS
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
        t.training_target_fall_before_conversion,
        t.training_label_eligible,
        t.fecha_pago_ci,
        t.pago_ci_marker_confirmado,
        t.monto_pago_ci_positivo,
        pr.proforma_first_seen_at
    FROM decision_intelligence.v_separation_fall_training_outcome t
    LEFT JOIN proforma_recency pr
      ON pr.codigo_proforma = t.codigo_proforma
    WHERE t.training_label_eligible
      AND t.training_target_fall_before_conversion IS NOT NULL
      AND t.fecha_separacion IS NOT NULL
      AND t.outcome_at IS NOT NULL
),
expanded AS (
    SELECT
        b.*,
        l.day_n AS landmark_day,
        (b.fecha_separacion::date + l.day_n) AS snapshot_at
    FROM base b
    CROSS JOIN landmarks l
),
eligibility AS (
    SELECT
        e.*,
        CASE
            WHEN e.proforma_first_seen_at IS NULL
                THEN 'BLOCKED_MISSING_PROFORMA_FIRST_SEEN_AT'
            WHEN e.proforma_first_seen_at::date > e.snapshot_at
                THEN 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
            WHEN e.proforma_first_seen_at < e.snapshot_at - interval '3 months'
                THEN 'EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS_AT_SNAPSHOT'
            WHEN e.outcome_at::date <= e.snapshot_at
                THEN 'EXCLUDED_OUTCOME_ALREADY_KNOWN_AT_SNAPSHOT'
            WHEN e.fecha_pago_ci IS NOT NULL
             AND e.fecha_pago_ci::date <= e.snapshot_at
                THEN 'EXCLUDED_DATED_PAYMENT_ALREADY_KNOWN_AT_SNAPSHOT'
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
            ELSE 'ELIGIBLE'
        END::text AS snapshot_eligibility_status
    FROM expanded e
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
    snapshot_eligibility_status,

    -- Allowed structural/temporal features known by snapshot_at.
    landmark_day::integer AS days_since_separation,
    greatest(0, snapshot_at - proforma_first_seen_at::date)::integer AS proforma_age_days_at_snapshot,
    greatest(0, fecha_separacion::date - proforma_first_seen_at::date)::integer AS proforma_age_days_at_separation,
    extract(isodow from snapshot_at)::integer AS snapshot_iso_weekday,
    extract(month from snapshot_at)::integer AS snapshot_month,

    -- Governed target. These columns are audit/label metadata, not features.
    training_target_fall_before_conversion AS target_fall_before_conversion,
    training_outcome_class,
    outcome_at,
    greatest(0, outcome_at::date - snapshot_at)::integer AS days_from_snapshot_to_outcome,

    -- Explicit anti-leakage metadata.
    false::boolean AS interaction_features_certified,
    'STRUCTURAL_TEMPORAL_ONLY_V1'::text AS feature_scope,
    'GROUP_SPLIT_BY_SEPARATION_ID_AND_OUT_OF_TIME_REQUIRED'::text AS evaluation_contract
FROM eligibility;

CREATE VIEW features.separation_fall_training_point_in_time AS
WITH eligible AS (
    SELECT *
    FROM features.v_separation_fall_training_point_in_time_audit
    WHERE snapshot_eligibility_status = 'ELIGIBLE'
), weighted AS (
    SELECT
        e.*,
        COUNT(*) OVER (PARTITION BY separation_id) AS snapshots_per_separation
    FROM eligible e
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
    landmark_day,

    -- Model-eligible v1 features.
    days_since_separation,
    proforma_age_days_at_snapshot,
    proforma_age_days_at_separation,
    snapshot_iso_weekday,
    snapshot_month,

    target_fall_before_conversion,
    snapshots_per_separation,
    (1.0 / nullif(snapshots_per_separation, 0))::numeric AS lifecycle_balancing_weight,

    feature_scope,
    interaction_features_certified,
    evaluation_contract
FROM weighted;

CREATE VIEW features.v_separation_fall_training_point_in_time_health AS
SELECT
    COUNT(*)::bigint AS snapshot_rows,
    COUNT(DISTINCT separation_id)::bigint AS distinct_lifecycles,
    COUNT(*) FILTER (WHERE target_fall_before_conversion = 1)::bigint AS fall_snapshot_rows,
    COUNT(*) FILTER (WHERE target_fall_before_conversion = 0)::bigint AS conversion_snapshot_rows,
    COUNT(DISTINCT separation_id) FILTER (WHERE target_fall_before_conversion = 1)::bigint AS fall_lifecycles,
    COUNT(DISTINCT separation_id) FILTER (WHERE target_fall_before_conversion = 0)::bigint AS conversion_lifecycles,
    MIN(snapshot_at) AS oldest_snapshot_at,
    MAX(snapshot_at) AS newest_snapshot_at,
    MIN(landmark_day)::integer AS min_landmark_day,
    MAX(landmark_day)::integer AS max_landmark_day,
    COUNT(*) FILTER (WHERE interaction_features_certified)::bigint AS rows_with_certified_interaction_features,
    COUNT(*) FILTER (WHERE snapshots_per_separation <= 0)::bigint AS invalid_snapshot_weight_rows,
    COUNT(*) FILTER (WHERE lifecycle_balancing_weight IS NULL)::bigint AS missing_lifecycle_weight_rows,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'EXCLUDED_OUTCOME_ALREADY_KNOWN_AT_SNAPSHOT'
    ) AS excluded_outcome_already_known,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'EXCLUDED_ENTREGA_ALREADY_STARTED_AT_SNAPSHOT'
    ) AS excluded_entrega_already_started,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'EXCLUDED_DATED_PAYMENT_ALREADY_KNOWN_AT_SNAPSHOT'
    ) AS excluded_dated_payment_already_known,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'BLOCKED_MISSING_PROFORMA_FIRST_SEEN_AT'
    ) AS blocked_missing_proforma_first_seen,
    (
        SELECT COUNT(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'BLOCKED_PROFORMA_AFTER_SNAPSHOT'
    ) AS blocked_proforma_after_snapshot
FROM features.separation_fall_training_point_in_time;

COMMENT ON VIEW features.v_separation_fall_training_point_in_time_audit IS
'Historical landmark snapshots with explicit point-in-time eligibility and target metadata. Post-outcome text/reason fields are intentionally absent.';

COMMENT ON VIEW features.separation_fall_training_point_in_time IS
'Leakage-controlled structural/temporal baseline training rows for separation_fall_risk. Requires grouped out-of-time evaluation by separation_id; interaction history is not yet certified.';

COMMENT ON VIEW features.v_separation_fall_training_point_in_time_health IS
'Quality and coverage counters for the first point-in-time supervised training dataset.';
