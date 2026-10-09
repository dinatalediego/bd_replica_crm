BEGIN;

-- ================================================================
-- Medallio v2.8.2 — Predictive Evidence Calibration
--
-- Objective:
-- 1) separate backtest evidence from forecasts actually issued,
-- 2) require explicit issuance timing for operational scoring,
-- 3) canonicalize one prediction per project×origin×target×horizon,
-- 4) audit source/grain before interpreting WAPE,
-- 5) never return WARN only because there are many bad observations.
-- ================================================================

CREATE OR REPLACE VIEW model_control.v_forecast_snapshot_classified AS
SELECT
    s.*,

    CASE
        WHEN coalesce(s.raw_metadata -> 'mapped_columns', '{}'::jsonb) ? 'selected'
            THEN 'SOURCE_FLAG'
        ELSE 'DEFAULT_TRUE'
    END AS selection_evidence,

    CASE
        WHEN s.source_relation = 'analytics.commercial_forecast_backtest'
            THEN 'BACKTEST_ONLY'

        WHEN s.capture_mode = 'CURRENT_CAPTURE'
         AND s.issuance_evidence = 'SOURCE_CREATED_AT'
            THEN 'PROSPECTIVE_ISSUED'

        WHEN s.source_relation = 'analytics.commercial_forecast_predictions'
         AND s.issuance_evidence = 'SOURCE_CREATED_AT'
         AND coalesce(s.raw_metadata -> 'mapped_columns', '{}'::jsonb) ? 'selected'
            THEN 'HISTORICAL_ISSUED'

        ELSE 'UNVERIFIED'
    END AS evidence_class,

    (
        s.issuance_evidence = 'SOURCE_CREATED_AT'
        AND s.issued_at IS NOT NULL
        AND s.issued_at::date < s.target_period
    ) AS strict_leakage_safe

FROM model_control.forecast_prediction_snapshot s;


CREATE OR REPLACE VIEW analytics.v_forecast_snapshot_cell_audit AS
SELECT
    source_relation,
    evidence_class,
    selection_evidence,
    issuance_evidence,

    count(*) AS snapshot_rows,

    count(
        DISTINCT concat_ws(
            '|',
            project_key,
            origin_period::text,
            target_period::text,
            horizon::text
        )
    ) AS distinct_cells,

    count(DISTINCT project_key) AS projects,

    count(*) FILTER (WHERE is_selected) AS selected_rows,
    count(*) FILTER (WHERE strict_leakage_safe) AS strict_leakage_safe_rows,

    round(
        count(*)::numeric
        / nullif(
            count(
                DISTINCT concat_ws(
                    '|',
                    project_key,
                    origin_period::text,
                    target_period::text,
                    horizon::text
                )
            ),
            0
        ),
        2
    ) AS rows_per_cell,

    min(prediction) AS min_prediction,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY prediction) AS median_prediction,
    max(prediction) AS max_prediction

FROM model_control.v_forecast_snapshot_classified
GROUP BY
    source_relation,
    evidence_class,
    selection_evidence,
    issuance_evidence
ORDER BY snapshot_rows DESC;


-- One operational forecast per project×origin×target×horizon.
-- Multiple reruns are allowed; the latest genuinely issued forecast
-- before the target month is the canonical version.
CREATE OR REPLACE VIEW model_control.v_forecast_prediction_canonical AS
WITH eligible AS (
    SELECT
        s.*,

        count(*) OVER (
            PARTITION BY
                project_key,
                origin_period,
                target_period,
                horizon
        ) AS candidate_rows,

        row_number() OVER (
            PARTITION BY
                project_key,
                origin_period,
                target_period,
                horizon
            ORDER BY
                CASE evidence_class
                    WHEN 'PROSPECTIVE_ISSUED' THEN 1
                    WHEN 'HISTORICAL_ISSUED' THEN 2
                    ELSE 9
                END,
                issued_at DESC NULLS LAST,
                forecast_snapshot_id DESC
        ) AS rn

    FROM model_control.v_forecast_snapshot_classified s
    WHERE s.is_selected
      AND s.strict_leakage_safe
      AND s.evidence_class IN (
          'PROSPECTIVE_ISSUED',
          'HISTORICAL_ISSUED'
      )
)
SELECT *
FROM eligible
WHERE rn = 1;


CREATE OR REPLACE VIEW analytics.v_forecast_evaluation_mature AS
SELECT
    -- Existing v2.8/v2.8.1 column contract: DO NOT reorder.
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
    s.strict_leakage_safe AS leakage_safe,
    true AS is_selected,

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

    true AS mature_for_evaluation,
    true AS eligible_for_operational_scoring,

    -- v2.8.2 additions: append only.
    s.evidence_class,
    s.selection_evidence

FROM model_control.v_forecast_prediction_canonical s
JOIN analytics.comercial_proyecto_mes a
  ON a.codigo_proyecto = s.project_key
 AND a.periodo_mes = s.target_period

WHERE s.target_period
      < date_trunc(
          'month',
          (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
        )::date
  AND NOT a.mes_parcial
  AND a.ventas_mes IS NOT NULL;


-- Diagnostic only: includes non-operational evidence to reveal
-- scale/grain problems without allowing it to promote L3.
CREATE OR REPLACE VIEW analytics.v_forecast_source_diagnostic AS
WITH pairs AS (
    SELECT
        s.source_relation,
        s.evidence_class,
        s.project_key,
        s.origin_period,
        s.target_period,
        s.horizon,
        s.prediction,
        a.ventas_mes::numeric AS actual,
        (s.prediction - a.ventas_mes::numeric) AS signed_error,
        abs(s.prediction - a.ventas_mes::numeric) AS absolute_error
    FROM model_control.v_forecast_snapshot_classified s
    JOIN analytics.comercial_proyecto_mes a
      ON a.codigo_proyecto = s.project_key
     AND a.periodo_mes = s.target_period
    WHERE s.is_selected
      AND s.target_period
          < date_trunc(
              'month',
              (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
            )::date
      AND NOT a.mes_parcial
      AND a.ventas_mes IS NOT NULL
)
SELECT
    source_relation,
    evidence_class,

    count(*) AS matched_rows,
    count(DISTINCT project_key) AS projects,
    count(
        DISTINCT concat_ws(
            '|',
            project_key,
            origin_period::text,
            target_period::text,
            horizon::text
        )
    ) AS distinct_cells,

    round(avg(prediction), 3) AS avg_prediction,
    round(avg(actual), 3) AS avg_actual,

    round(
        sum(prediction)
        / nullif(sum(actual), 0),
        3
    ) AS prediction_to_actual_ratio,

    round(
        100.0 * sum(absolute_error)
        / nullif(sum(abs(actual)), 0),
        3
    ) AS diagnostic_wape_pct,

    round(
        100.0 * sum(signed_error)
        / nullif(sum(abs(actual)), 0),
        3
    ) AS diagnostic_bias_pct

FROM pairs
GROUP BY source_relation, evidence_class
ORDER BY matched_rows DESC;


CREATE OR REPLACE VIEW analytics.v_forecast_performance_by_project_horizon AS
WITH agg AS (
    SELECT
        project_key,
        horizon,

        count(*) AS mature_pairs,
        count(*) FILTER (WHERE leakage_safe) AS leakage_safe_pairs,

        sum(abs(actual)) AS sum_abs_actual,
        sum(absolute_error) AS sum_abs_error,
        sum(signed_error) AS sum_signed_error,

        avg(absolute_error) AS mae,
        sqrt(avg(power(signed_error, 2))) AS rmse,
        avg(ape_pct) FILTER (WHERE ape_pct IS NOT NULL) AS mape_pct,

        min(origin_period) AS first_origin_period,
        max(origin_period) AS last_origin_period,
        max(target_period) AS latest_mature_target,
        count(DISTINCT run_id) AS distinct_runs

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
         AND 100.0 * sum_abs_error / nullif(sum_abs_actual, 0) <= 50
         AND abs(100.0 * sum_signed_error / nullif(sum_abs_actual, 0)) <= 30
        THEN 'WATCH'

        ELSE 'NOT_DEFENSIBLE'
    END AS defense_status

FROM agg;


CREATE OR REPLACE VIEW analytics.v_forecast_predictive_gate AS
WITH operational AS (
    SELECT
        count(*) AS cells,

        count(*) FILTER (
            WHERE defense_status = 'DEFENSIBLE'
        ) AS defensible_cells,

        count(DISTINCT project_key) FILTER (
            WHERE mature_pairs > 0
        ) AS projects_with_mature,

        coalesce(sum(mature_pairs), 0) AS mature_pairs,
        coalesce(sum(leakage_safe_pairs), 0) AS leakage_safe_pairs

    FROM analytics.v_forecast_performance_by_project_horizon
),
metrics AS (
    SELECT
        sum(abs(actual)) AS sum_abs_actual,
        sum(absolute_error) AS sum_abs_error,
        sum(signed_error) AS sum_signed_error,
        count(*) FILTER (WHERE leakage_safe) AS leakage_safe_pair_rows,
        count(*) AS mature_pair_rows
    FROM analytics.v_forecast_evaluation_mature
),
inventory AS (
    SELECT
        count(*) AS snapshot_rows,

        count(*) FILTER (
            WHERE evidence_class = 'BACKTEST_ONLY'
        ) AS backtest_only_rows,

        count(*) FILTER (
            WHERE evidence_class = 'UNVERIFIED'
        ) AS unverified_rows,

        count(*) FILTER (
            WHERE evidence_class IN (
                'HISTORICAL_ISSUED',
                'PROSPECTIVE_ISSUED'
            )
        ) AS issued_evidence_rows

    FROM model_control.v_forecast_snapshot_classified
),
base AS (
    SELECT
        -- Preserve v2.8/v2.8.1 public column order.
        o.cells,
        o.defensible_cells,
        o.projects_with_mature,
        o.mature_pairs,
        o.leakage_safe_pairs,

        100.0 * m.sum_abs_error
            / nullif(m.sum_abs_actual, 0) AS global_wape_pct,

        100.0 * m.sum_signed_error
            / nullif(m.sum_abs_actual, 0) AS global_bias_pct,

        100.0 * m.leakage_safe_pair_rows
            / nullif(m.mature_pair_rows, 0) AS leakage_safe_pct,

        -- v2.8.2 inventory appended after the original contract.
        i.snapshot_rows,
        i.backtest_only_rows,
        i.unverified_rows,
        i.issued_evidence_rows

    FROM operational o
    CROSS JOIN metrics m
    CROSS JOIN inventory i
),
scored AS (
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
             AND defensible_cells >= 1
             AND global_wape_pct <= 50
             AND abs(global_bias_pct) <= 30
             AND leakage_safe_pct = 100
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
             AND defensible_cells >= 1
             AND global_wape_pct <= 50
             AND abs(global_bias_pct) <= 30
             AND leakage_safe_pct = 100
            THEN 50

            ELSE 0
        END AS gate_score,

        CASE
            WHEN mature_pairs = 0
            THEN concat(
                'No existen pares forecast→actual con evidencia de emisión verificable. ',
                'Backtest-only=', backtest_only_rows,
                '; unverified=', unverified_rows, '.'
            )

            WHEN global_wape_pct > 50
            THEN concat(
                'WAPE operacional ',
                round(global_wape_pct, 1),
                '% es demasiado alto para WARN; L3 queda BLOCK.'
            )

            WHEN abs(global_bias_pct) > 30
            THEN concat(
                'Bias operacional ',
                round(global_bias_pct, 1),
                '% es demasiado alto para WARN; L3 queda BLOCK.'
            )

            WHEN mature_pairs < 6
            THEN concat(
                'Sólo existen ', mature_pairs,
                ' pares operacionales maduros; WARN requiere al menos 6.'
            )

            WHEN projects_with_mature < 2
            THEN concat(
                'La evidencia operacional madura cubre sólo ',
                projects_with_mature,
                ' proyectos.'
            )

            WHEN defensible_cells = 0
            THEN 'No existe ninguna celda proyecto×horizonte defendible.'

            WHEN global_wape_pct > 25
            THEN concat(
                'WAPE operacional ',
                round(global_wape_pct, 1),
                '% aún supera el umbral PASS de 25%.'
            )

            WHEN abs(global_bias_pct) > 15
            THEN concat(
                'Bias operacional ',
                round(global_bias_pct, 1),
                '% aún supera ±15%.'
            )

            WHEN defensible_cells < 3
            THEN concat(
                'Sólo ', defensible_cells,
                ' celdas proyecto×horizonte son defendibles; PASS requiere 3.'
            )

            ELSE 'Forecast defendible sobre evidencia emitida, madura y leakage-safe.'
        END AS gate_reason

    FROM base
)
SELECT
    -- Original v2.8/v2.8.1 columns in the exact same order.
    cells,
    defensible_cells,
    projects_with_mature,
    mature_pairs,
    leakage_safe_pairs,
    global_wape_pct,
    global_bias_pct,
    leakage_safe_pct,
    gate_status,
    gate_score,
    gate_reason,

    -- v2.8.2 additions appended only.
    snapshot_rows,
    backtest_only_rows,
    unverified_rows,
    issued_evidence_rows

FROM scored;


CREATE OR REPLACE VIEW analytics.v_forecast_defensible AS
SELECT *
FROM analytics.v_forecast_performance_by_project_horizon
WHERE defense_status = 'DEFENSIBLE'
ORDER BY wape_pct, abs(bias_pct), mature_pairs DESC;


COMMENT ON VIEW model_control.v_forecast_snapshot_classified IS
'Clasifica snapshots como PROSPECTIVE_ISSUED, HISTORICAL_ISSUED, BACKTEST_ONLY o UNVERIFIED. Sólo evidencia emitida puede promover L3.';

COMMENT ON VIEW analytics.v_forecast_source_diagnostic IS
'Auditoría de fuente/grano. Sus métricas NO promueven L3; sirven para detectar escalas, duplicados y backtests retrospectivos.';

COMMENT ON VIEW analytics.v_forecast_predictive_gate IS
'Gate L3 calibrado. Mucha evidencia con WAPE/Bias catastróficos permanece BLOCK; WARN requiere precisión intermedia y al menos una celda defendible.';

COMMIT;
