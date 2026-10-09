BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS model_control;

CREATE TABLE IF NOT EXISTS model_control.forecast_prediction_snapshot (
    forecast_snapshot_id bigserial PRIMARY KEY,
    source_hash text NOT NULL UNIQUE,
    source_relation text NOT NULL,
    capture_mode text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),

    run_id text,
    project_key text NOT NULL,
    origin_period date,
    target_period date NOT NULL,
    horizon integer NOT NULL CHECK (horizon >= 1),
    prediction numeric NOT NULL,

    issued_at timestamptz,
    issuance_evidence text,
    leakage_safe boolean,

    is_selected boolean,
    model_name text,
    model_version text,

    stock_at_origin numeric,
    target_sales numeric,
    expected_shortfall numeric,

    raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_forecast_prediction_snapshot_project_target
ON model_control.forecast_prediction_snapshot(project_key, target_period, horizon);

CREATE INDEX IF NOT EXISTS ix_forecast_prediction_snapshot_origin
ON model_control.forecast_prediction_snapshot(origin_period, horizon);

CREATE INDEX IF NOT EXISTS ix_forecast_prediction_snapshot_selected
ON model_control.forecast_prediction_snapshot(is_selected)
WHERE is_selected IS TRUE;


-- Mature means:
-- 1) the target month is before the current Lima month,
-- 2) the commercial month is explicitly complete,
-- 3) an actual value exists,
-- 4) the forecast was issued before the target month started.
CREATE OR REPLACE VIEW analytics.v_forecast_evaluation_mature AS
SELECT
    s.forecast_snapshot_id,
    s.source_hash,
    s.source_relation,
    s.capture_mode,
    s.run_id,
    s.project_key,
    s.origin_period,
    s.target_period,
    s.horizon,
    s.prediction,
    a.ventas_mes::numeric AS actual,

    (s.prediction - a.ventas_mes::numeric) AS signed_error,
    abs(s.prediction - a.ventas_mes::numeric) AS absolute_error,
    CASE
        WHEN abs(a.ventas_mes::numeric) > 0
        THEN abs(s.prediction - a.ventas_mes::numeric)
             / abs(a.ventas_mes::numeric) * 100
    END AS ape_pct,

    s.issued_at,
    s.issuance_evidence,
    s.leakage_safe,
    coalesce(s.is_selected, true) AS is_selected,

    s.model_name,
    s.model_version,
    s.stock_at_origin,
    s.target_sales,
    s.expected_shortfall,

    a.stock_inicial::numeric AS actual_stock_open,
    a.stock_final::numeric AS actual_stock_close,
    a.absorcion_mes::numeric AS actual_absorption_rate,
    a.mes_vida,
    a.fecha_corte AS actual_cutoff_date,

    (
        s.target_period
        < date_trunc(
            'month',
            (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
          )::date
        AND NOT a.mes_parcial
        AND a.ventas_mes IS NOT NULL
    ) AS mature_for_evaluation,

    (
        coalesce(s.leakage_safe, false)
        AND s.target_period
            < date_trunc(
                'month',
                (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
              )::date
        AND NOT a.mes_parcial
        AND a.ventas_mes IS NOT NULL
    ) AS eligible_for_operational_scoring

FROM model_control.forecast_prediction_snapshot s
JOIN analytics.comercial_proyecto_mes a
  ON a.codigo_proyecto = s.project_key
 AND a.periodo_mes = s.target_period

WHERE coalesce(s.is_selected, true)
  AND s.target_period
      < date_trunc(
          'month',
          (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
        )::date
  AND NOT a.mes_parcial
  AND a.ventas_mes IS NOT NULL;


CREATE OR REPLACE VIEW analytics.v_forecast_performance_by_project_horizon AS
WITH agg AS (
    SELECT
        project_key,
        horizon,

        count(*) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS mature_pairs,

        count(*) FILTER (
            WHERE eligible_for_operational_scoring
              AND leakage_safe
        ) AS leakage_safe_pairs,

        sum(abs(actual)) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS sum_abs_actual,

        sum(absolute_error) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS sum_abs_error,

        sum(signed_error) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS sum_signed_error,

        avg(absolute_error) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS mae,

        sqrt(
            avg(power(signed_error, 2))
            FILTER (WHERE eligible_for_operational_scoring)
        ) AS rmse,

        avg(ape_pct) FILTER (
            WHERE eligible_for_operational_scoring
              AND ape_pct IS NOT NULL
        ) AS mape_pct,

        min(origin_period) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS first_origin_period,

        max(origin_period) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS last_origin_period,

        max(target_period) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS latest_mature_target,

        count(DISTINCT run_id) FILTER (
            WHERE eligible_for_operational_scoring
        ) AS distinct_runs

    FROM analytics.v_forecast_evaluation_mature
    GROUP BY project_key, horizon
)
SELECT
    project_key,
    horizon,
    mature_pairs,
    leakage_safe_pairs,
    distinct_runs,

    100.0 * sum_abs_error / nullif(sum_abs_actual, 0) AS wape_pct,
    100.0 * sum_signed_error / nullif(sum_abs_actual, 0) AS bias_pct,

    mae,
    rmse,
    mape_pct,

    100.0 * leakage_safe_pairs / nullif(mature_pairs, 0) AS leakage_safe_pct,

    first_origin_period,
    last_origin_period,
    latest_mature_target,

    CASE
        WHEN mature_pairs >= 3
         AND 100.0 * sum_abs_error / nullif(sum_abs_actual, 0) <= 25
         AND abs(100.0 * sum_signed_error / nullif(sum_abs_actual, 0)) <= 15
         AND 100.0 * leakage_safe_pairs / nullif(mature_pairs, 0) = 100
        THEN 'DEFENSIBLE'

        WHEN mature_pairs >= 2
        THEN 'WATCH'

        ELSE 'INSUFFICIENT'
    END AS defense_status

FROM agg;


CREATE OR REPLACE VIEW analytics.v_forecast_predictive_gate AS
WITH cells AS (
    SELECT *
    FROM analytics.v_forecast_performance_by_project_horizon
),
totals AS (
    SELECT
        count(*) AS cells,
        count(*) FILTER (WHERE defense_status = 'DEFENSIBLE') AS defensible_cells,
        count(DISTINCT project_key) FILTER (WHERE mature_pairs > 0) AS projects_with_mature,

        coalesce(sum(mature_pairs), 0) AS mature_pairs,
        coalesce(sum(leakage_safe_pairs), 0) AS leakage_safe_pairs,

        sum(sum_abs_actual) AS sum_abs_actual_internal,
        sum(sum_abs_error) AS sum_abs_error_internal,
        sum(sum_signed_error) AS sum_signed_error_internal

    FROM (
        SELECT
            p.*,
            -- reconstruct weighted components from metrics for gate aggregation
            e.sum_abs_actual,
            e.sum_abs_error,
            e.sum_signed_error
        FROM cells p
        JOIN (
            SELECT
                project_key,
                horizon,
                sum(abs(actual)) FILTER (
                    WHERE eligible_for_operational_scoring
                ) AS sum_abs_actual,
                sum(absolute_error) FILTER (
                    WHERE eligible_for_operational_scoring
                ) AS sum_abs_error,
                sum(signed_error) FILTER (
                    WHERE eligible_for_operational_scoring
                ) AS sum_signed_error
            FROM analytics.v_forecast_evaluation_mature
            GROUP BY project_key, horizon
        ) e USING (project_key, horizon)
    ) x
),
scored AS (
    SELECT
        cells,
        defensible_cells,
        projects_with_mature,
        mature_pairs,
        leakage_safe_pairs,

        100.0 * sum_abs_error_internal
            / nullif(sum_abs_actual_internal, 0) AS global_wape_pct,

        100.0 * sum_signed_error_internal
            / nullif(sum_abs_actual_internal, 0) AS global_bias_pct,

        100.0 * leakage_safe_pairs
            / nullif(mature_pairs, 0) AS leakage_safe_pct

    FROM totals
)
SELECT
    *,
    CASE
        WHEN mature_pairs >= 12
         AND projects_with_mature >= 3
         AND defensible_cells >= 3
         AND global_wape_pct <= 25
         AND abs(global_bias_pct) <= 15
         AND leakage_safe_pct = 100
        THEN 'PASS'

        WHEN mature_pairs >= 6
         AND projects_with_mature >= 2
        THEN 'WARN'

        ELSE 'BLOCK'
    END AS gate_status,

    CASE
        WHEN mature_pairs >= 12
         AND projects_with_mature >= 3
         AND defensible_cells >= 3
         AND global_wape_pct <= 25
         AND abs(global_bias_pct) <= 15
         AND leakage_safe_pct = 100
        THEN 100

        WHEN mature_pairs >= 6
         AND projects_with_mature >= 2
        THEN 50

        ELSE 0
    END AS gate_score,

    CASE
        WHEN mature_pairs = 0
        THEN 'No existen pares forecast→actual maduros y leakage-safe.'

        WHEN mature_pairs < 6
        THEN format(
            'Sólo existen %s pares maduros; se requieren al menos 6 para entrar en WATCH y 12 para PASS.',
            mature_pairs
        )

        WHEN projects_with_mature < 3
        THEN format(
            'La evidencia madura cubre %s proyectos; PASS requiere al menos 3.',
            projects_with_mature
        )

        WHEN global_wape_pct > 25
        THEN concat(
            'WAPE global maduro ',
            round(global_wape_pct, 1),
            '% supera el umbral CEO de 25%.'
        )

        WHEN abs(global_bias_pct) > 15
        THEN concat(
            'Bias global maduro ',
            round(global_bias_pct, 1),
            '% supera ±15%.'
        )

        WHEN leakage_safe_pct < 100
        THEN concat(
            'Sólo ',
            round(leakage_safe_pct, 1),
            '% de los pares maduros cumplen control leakage-safe.'
        )

        WHEN defensible_cells < 3
        THEN format(
            'Sólo %s celdas proyecto×horizonte son defendibles; PASS requiere 3.',
            defensible_cells
        )

        ELSE 'Forecast validado sobre outcomes maduros, con precisión, sesgo y leakage dentro de política.'
    END AS gate_reason

FROM scored;


CREATE OR REPLACE VIEW analytics.v_forecast_defensible AS
SELECT *
FROM analytics.v_forecast_performance_by_project_horizon
WHERE defense_status = 'DEFENSIBLE'
ORDER BY wape_pct, abs(bias_pct), mature_pairs DESC;


COMMENT ON TABLE model_control.forecast_prediction_snapshot IS
'Forecast emitido y congelado antes de conocer el outcome. Fuente histórica/corriente estandarizada por proyecto×origen×horizonte.';

COMMENT ON VIEW analytics.v_forecast_evaluation_mature IS
'Matching forecast→actual usando únicamente meses comerciales completos y control leakage-safe.';

COMMENT ON VIEW analytics.v_forecast_performance_by_project_horizon IS
'WAPE/Bias/MAE/RMSE por proyecto×horizonte sobre outcomes maduros. DEFENSIBLE requiere n>=3, WAPE<=25%, |Bias|<=15% y 100% leakage-safe.';

COMMENT ON VIEW analytics.v_forecast_predictive_gate IS
'Gate CEO L3. PASS: >=12 pares maduros, >=3 proyectos, >=3 celdas defendibles, WAPE<=25%, |Bias|<=15%, 100% leakage-safe.';

COMMIT;
