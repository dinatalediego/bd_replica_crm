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

FROM scored;;
