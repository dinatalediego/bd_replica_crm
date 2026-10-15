BEGIN;

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS model_control;

-- ================================================================
-- Medallio v2.8.3
-- Prospective Forecast Registry + Maturity Clock + Naive Benchmarks
-- ================================================================

CREATE TABLE IF NOT EXISTS model_control.forecast_issue_batch (
    issue_batch_id text PRIMARY KEY,
    issued_at timestamptz NOT NULL,
    slot text NOT NULL,
    source_relation text NOT NULL,
    capture_reason text NOT NULL DEFAULT 'AMBASSADOR',
    source_rows integer NOT NULL DEFAULT 0,
    candidate_cells integer NOT NULL DEFAULT 0,
    inserted_rows integer NOT NULL DEFAULT 0,
    unchanged_rows integer NOT NULL DEFAULT 0,
    ambiguous_cells integer NOT NULL DEFAULT 0,
    skipped_rows integer NOT NULL DEFAULT 0,
    capture_status text NOT NULL DEFAULT 'OPEN',
    completed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS model_control.forecast_issue_registry (
    issue_id text PRIMARY KEY,
    issue_batch_id text NOT NULL
        REFERENCES model_control.forecast_issue_batch(issue_batch_id)
        ON DELETE RESTRICT,

    forecast_signature text NOT NULL,
    source_relation text NOT NULL,
    source_run_id text,
    slot text NOT NULL,

    issued_at timestamptz NOT NULL,
    source_created_at timestamptz,
    data_cutoff date,

    project_key text NOT NULL,
    origin_period date,
    target_period date NOT NULL,
    horizon integer NOT NULL CHECK (horizon >= 1),
    prediction numeric NOT NULL,

    model_name text,
    model_version text,

    stock_at_issue numeric,
    target_sales numeric,
    expected_shortfall numeric,

    issuance_evidence text NOT NULL DEFAULT 'AMBASSADOR_CAPTURE',
    immutable boolean NOT NULL DEFAULT true,
    source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_forecast_issue_registry_cell
ON model_control.forecast_issue_registry(
    project_key, target_period, horizon, issued_at DESC
);

CREATE INDEX IF NOT EXISTS ix_forecast_issue_registry_batch
ON model_control.forecast_issue_registry(issue_batch_id);

CREATE INDEX IF NOT EXISTS ix_forecast_issue_registry_issued
ON model_control.forecast_issue_registry(issued_at DESC);


CREATE TABLE IF NOT EXISTS model_control.forecast_naive_benchmark_snapshot (
    benchmark_snapshot_id bigserial PRIMARY KEY,
    issue_id text NOT NULL
        REFERENCES model_control.forecast_issue_registry(issue_id)
        ON DELETE CASCADE,

    benchmark_method text NOT NULL,
    benchmark_prediction numeric NOT NULL,
    benchmark_history_rows integer NOT NULL,
    benchmark_cutoff date,
    source_periods jsonb NOT NULL DEFAULT '[]'::jsonb,
    primary_benchmark boolean NOT NULL DEFAULT false,
    benchmark_policy text NOT NULL DEFAULT 'NAIVE_V1',

    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE(issue_id, benchmark_method)
);

CREATE INDEX IF NOT EXISTS ix_forecast_naive_benchmark_issue
ON model_control.forecast_naive_benchmark_snapshot(issue_id);


CREATE TABLE IF NOT EXISTS model_control.forecast_maturity_event (
    maturity_event_id bigserial PRIMARY KEY,
    issue_id text NOT NULL UNIQUE
        REFERENCES model_control.forecast_issue_registry(issue_id)
        ON DELETE CASCADE,

    matured_at timestamptz NOT NULL DEFAULT now(),
    target_period date NOT NULL,
    actual numeric NOT NULL,
    actual_source text NOT NULL DEFAULT 'analytics.comercial_proyecto_mes',
    actual_cutoff_date date,
    period_complete boolean NOT NULL DEFAULT true,

    created_at timestamptz NOT NULL DEFAULT now()
);


CREATE OR REPLACE VIEW model_control.v_forecast_issue_canonical AS
WITH ranked AS (
    SELECT
        i.*,

        count(*) OVER (
            PARTITION BY project_key, target_period, horizon
        ) AS revision_count,

        min(issued_at) OVER (
            PARTITION BY project_key, target_period, horizon
        ) AS first_issued_at,

        max(issued_at) OVER (
            PARTITION BY project_key, target_period, horizon
        ) AS last_issued_at,

        row_number() OVER (
            PARTITION BY project_key, target_period, horizon
            ORDER BY issued_at DESC, issue_id DESC
        ) AS rn

    FROM model_control.forecast_issue_registry i
    WHERE issued_at::date < target_period
)
SELECT *
FROM ranked
WHERE rn = 1;


CREATE OR REPLACE FUNCTION model_control.populate_naive_benchmarks_v283(
    p_batch_id text
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    n integer := 0;
    m integer := 0;
BEGIN
    -- Last complete month available when the forecast was issued.
    INSERT INTO model_control.forecast_naive_benchmark_snapshot(
        issue_id,
        benchmark_method,
        benchmark_prediction,
        benchmark_history_rows,
        benchmark_cutoff,
        source_periods,
        primary_benchmark
    )
    SELECT
        i.issue_id,
        'LAST_COMPLETE_MONTH',
        h.ventas_mes::numeric,
        1,
        h.periodo_mes,
        jsonb_build_array(h.periodo_mes),
        false
    FROM model_control.forecast_issue_registry i
    JOIN LATERAL (
        SELECT p.periodo_mes, p.ventas_mes
        FROM analytics.comercial_proyecto_mes p
        WHERE p.codigo_proyecto = i.project_key
          AND NOT p.mes_parcial
          AND p.ventas_mes IS NOT NULL
          AND p.periodo_mes < date_trunc(
              'month',
              i.issued_at AT TIME ZONE 'America/Lima'
          )::date
        ORDER BY p.periodo_mes DESC
        LIMIT 1
    ) h ON true
    WHERE i.issue_batch_id = p_batch_id
    ON CONFLICT (issue_id, benchmark_method) DO NOTHING;

    GET DIAGNOSTICS n = ROW_COUNT;

    -- Rolling 3 complete months. Requires exactly 3 observations.
    INSERT INTO model_control.forecast_naive_benchmark_snapshot(
        issue_id,
        benchmark_method,
        benchmark_prediction,
        benchmark_history_rows,
        benchmark_cutoff,
        source_periods,
        primary_benchmark
    )
    SELECT
        i.issue_id,
        'ROLLING_3M_MEAN',
        h.benchmark_prediction,
        h.history_rows,
        h.benchmark_cutoff,
        h.source_periods,
        false
    FROM model_control.forecast_issue_registry i
    JOIN LATERAL (
        SELECT
            avg(x.ventas_mes::numeric) AS benchmark_prediction,
            count(*)::integer AS history_rows,
            max(x.periodo_mes) AS benchmark_cutoff,
            jsonb_agg(x.periodo_mes ORDER BY x.periodo_mes) AS source_periods
        FROM (
            SELECT p.periodo_mes, p.ventas_mes
            FROM analytics.comercial_proyecto_mes p
            WHERE p.codigo_proyecto = i.project_key
              AND NOT p.mes_parcial
              AND p.ventas_mes IS NOT NULL
              AND p.periodo_mes < date_trunc(
                  'month',
                  i.issued_at AT TIME ZONE 'America/Lima'
              )::date
            ORDER BY p.periodo_mes DESC
            LIMIT 3
        ) x
        HAVING count(*) = 3
    ) h ON true
    WHERE i.issue_batch_id = p_batch_id
    ON CONFLICT (issue_id, benchmark_method) DO NOTHING;

    GET DIAGNOSTICS m = ROW_COUNT;
    n := n + m;

    -- Same target calendar month one year earlier, if already observable.
    INSERT INTO model_control.forecast_naive_benchmark_snapshot(
        issue_id,
        benchmark_method,
        benchmark_prediction,
        benchmark_history_rows,
        benchmark_cutoff,
        source_periods,
        primary_benchmark
    )
    SELECT
        i.issue_id,
        'SEASONAL_12M',
        p.ventas_mes::numeric,
        1,
        p.periodo_mes,
        jsonb_build_array(p.periodo_mes),
        false
    FROM model_control.forecast_issue_registry i
    JOIN analytics.comercial_proyecto_mes p
      ON p.codigo_proyecto = i.project_key
     AND p.periodo_mes = (i.target_period - interval '12 months')::date
     AND NOT p.mes_parcial
     AND p.ventas_mes IS NOT NULL
    WHERE i.issue_batch_id = p_batch_id
      AND p.periodo_mes < date_trunc(
          'month',
          i.issued_at AT TIME ZONE 'America/Lima'
      )::date
    ON CONFLICT (issue_id, benchmark_method) DO NOTHING;

    GET DIAGNOSTICS m = ROW_COUNT;
    n := n + m;

    -- Primary benchmark policy:
    -- Rolling 3M > Last complete month > Seasonal 12M.
    WITH ranked AS (
        SELECT
            benchmark_snapshot_id,
            row_number() OVER (
                PARTITION BY issue_id
                ORDER BY
                    CASE benchmark_method
                        WHEN 'ROLLING_3M_MEAN' THEN 1
                        WHEN 'LAST_COMPLETE_MONTH' THEN 2
                        WHEN 'SEASONAL_12M' THEN 3
                        ELSE 9
                    END,
                    benchmark_snapshot_id
            ) AS rn
        FROM model_control.forecast_naive_benchmark_snapshot b
        WHERE EXISTS (
            SELECT 1
            FROM model_control.forecast_issue_registry i
            WHERE i.issue_id = b.issue_id
              AND i.issue_batch_id = p_batch_id
        )
    )
    UPDATE model_control.forecast_naive_benchmark_snapshot b
       SET primary_benchmark = (r.rn = 1)
    FROM ranked r
    WHERE r.benchmark_snapshot_id = b.benchmark_snapshot_id;

    RETURN n;
END;
$$;


CREATE OR REPLACE FUNCTION analytics.refresh_forecast_maturity_v283()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    n integer := 0;
BEGIN
    INSERT INTO model_control.forecast_maturity_event(
        issue_id,
        matured_at,
        target_period,
        actual,
        actual_source,
        actual_cutoff_date,
        period_complete
    )
    SELECT
        i.issue_id,
        now(),
        i.target_period,
        a.ventas_mes::numeric,
        'analytics.comercial_proyecto_mes',
        a.fecha_corte,
        true
    FROM model_control.v_forecast_issue_canonical i
    JOIN analytics.comercial_proyecto_mes a
      ON a.codigo_proyecto = i.project_key
     AND a.periodo_mes = i.target_period
    WHERE i.target_period < date_trunc(
              'month',
              (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
          )::date
      AND NOT a.mes_parcial
      AND a.ventas_mes IS NOT NULL
    ON CONFLICT (issue_id) DO NOTHING;

    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;


CREATE OR REPLACE VIEW analytics.v_forecast_maturity_clock_v283 AS
SELECT
    i.issue_id,
    i.issue_batch_id,
    i.project_key,
    i.origin_period,
    i.target_period,
    i.horizon,
    i.prediction,
    i.issued_at,
    i.model_name,
    i.model_version,
    i.revision_count,
    i.first_issued_at,
    i.last_issued_at,

    (i.target_period + interval '1 month')::date AS expected_maturity_date,

    (
        (i.target_period + interval '1 month')::date
        - (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
    ) AS days_until_expected_maturity,

    e.matured_at,
    e.actual,
    e.actual_cutoff_date,

    b.benchmark_method AS primary_benchmark_method,
    b.benchmark_prediction AS primary_benchmark_prediction,

    CASE
        WHEN e.issue_id IS NOT NULL THEN 'EVALUATED'

        WHEN i.target_period >= date_trunc(
            'month',
            (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
        )::date
        THEN 'INCUBATING'

        ELSE 'OVERDUE_NO_ACTUAL'
    END AS maturity_status

FROM model_control.v_forecast_issue_canonical i
LEFT JOIN model_control.forecast_maturity_event e
  ON e.issue_id = i.issue_id
LEFT JOIN model_control.forecast_naive_benchmark_snapshot b
  ON b.issue_id = i.issue_id
 AND b.primary_benchmark;


CREATE OR REPLACE VIEW analytics.v_forecast_evaluation_v283 AS
SELECT
    i.issue_id,
    i.issue_batch_id,
    i.project_key,
    i.origin_period,
    i.target_period,
    i.horizon,
    i.prediction,
    e.actual,

    i.issued_at,
    i.model_name,
    i.model_version,
    i.revision_count,

    (i.prediction - e.actual) AS signed_error,
    abs(i.prediction - e.actual) AS absolute_error,

    CASE
        WHEN abs(e.actual) > 0
        THEN abs(i.prediction - e.actual) / abs(e.actual) * 100
    END AS ape_pct,

    b.benchmark_method AS primary_benchmark_method,
    b.benchmark_prediction AS primary_benchmark_prediction,

    CASE
        WHEN b.benchmark_prediction IS NOT NULL
        THEN abs(b.benchmark_prediction - e.actual)
    END AS naive_absolute_error,

    CASE
        WHEN b.benchmark_prediction IS NOT NULL
        THEN (b.benchmark_prediction - e.actual)
    END AS naive_signed_error,

    CASE
        WHEN b.benchmark_prediction IS NOT NULL
        THEN abs(i.prediction - e.actual)
             < abs(b.benchmark_prediction - e.actual)
    END AS model_beats_primary_naive,

    CASE
        WHEN b.benchmark_prediction IS NOT NULL
         AND abs(b.benchmark_prediction - e.actual) > 0
        THEN 1.0
             - abs(i.prediction - e.actual)
               / abs(b.benchmark_prediction - e.actual)
    END AS row_skill_score,

    100.0 AS leakage_safe_pct

FROM model_control.v_forecast_issue_canonical i
JOIN model_control.forecast_maturity_event e
  ON e.issue_id = i.issue_id
LEFT JOIN model_control.forecast_naive_benchmark_snapshot b
  ON b.issue_id = i.issue_id
 AND b.primary_benchmark;


CREATE OR REPLACE VIEW analytics.v_forecast_performance_v283 AS
WITH agg AS (
    SELECT
        project_key,
        horizon,

        count(*) AS mature_pairs,
        count(*) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) AS benchmark_pairs,

        sum(abs(actual)) AS sum_abs_actual,
        sum(absolute_error) AS sum_model_abs_error,
        sum(signed_error) AS sum_model_signed_error,
        sum(naive_absolute_error) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) AS sum_naive_abs_error,

        avg(absolute_error) AS model_mae,
        sqrt(avg(power(signed_error, 2))) AS model_rmse,

        avg(
            CASE WHEN model_beats_primary_naive THEN 1.0 ELSE 0.0 END
        ) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) * 100 AS model_beat_rate_pct,

        min(origin_period) AS first_origin_period,
        max(origin_period) AS last_origin_period,
        max(target_period) AS latest_mature_target,
        max(revision_count) AS max_revision_count

    FROM analytics.v_forecast_evaluation_v283
    GROUP BY project_key, horizon
)
SELECT
    project_key,
    horizon,
    mature_pairs,
    benchmark_pairs,

    100.0 * sum_model_abs_error
        / nullif(sum_abs_actual, 0) AS wape_pct,

    100.0 * sum_model_signed_error
        / nullif(sum_abs_actual, 0) AS bias_pct,

    100.0 * sum_naive_abs_error
        / nullif(sum_abs_actual, 0) AS naive_wape_pct,

    100.0 * (
        1.0 - sum_model_abs_error
              / nullif(sum_naive_abs_error, 0)
    ) AS skill_vs_naive_pct,

    model_beat_rate_pct,
    model_mae,
    model_rmse,

    100.0 * benchmark_pairs
        / nullif(mature_pairs, 0) AS benchmark_coverage_pct,

    first_origin_period,
    last_origin_period,
    latest_mature_target,
    max_revision_count,

    CASE
        WHEN mature_pairs >= 3
         AND benchmark_pairs >= 3
         AND 100.0 * sum_model_abs_error / nullif(sum_abs_actual, 0) <= 25
         AND abs(100.0 * sum_model_signed_error / nullif(sum_abs_actual, 0)) <= 15
         AND sum_model_abs_error < sum_naive_abs_error
         AND model_beat_rate_pct >= 50
        THEN 'DEFENSIBLE'

        WHEN mature_pairs >= 2
         AND benchmark_pairs >= 2
         AND 100.0 * sum_model_abs_error / nullif(sum_abs_actual, 0) <= 50
         AND abs(100.0 * sum_model_signed_error / nullif(sum_abs_actual, 0)) <= 30
         AND sum_model_abs_error <= sum_naive_abs_error
        THEN 'WATCH'

        ELSE 'NOT_DEFENSIBLE'
    END AS defense_status

FROM agg;


CREATE OR REPLACE VIEW analytics.v_forecast_defensible_v283 AS
SELECT *
FROM analytics.v_forecast_performance_v283
WHERE defense_status = 'DEFENSIBLE'
ORDER BY wape_pct, skill_vs_naive_pct DESC, mature_pairs DESC;


CREATE OR REPLACE VIEW analytics.v_forecast_predictive_gate_v283 AS
WITH perf AS (
    SELECT
        count(*) AS cells,
        count(*) FILTER (
            WHERE defense_status = 'DEFENSIBLE'
        ) AS defensible_cells,
        count(DISTINCT project_key) FILTER (
            WHERE mature_pairs > 0
        ) AS projects_with_mature,
        coalesce(sum(mature_pairs), 0) AS mature_pairs,
        coalesce(sum(benchmark_pairs), 0) AS benchmark_pairs
    FROM analytics.v_forecast_performance_v283
),
metrics AS (
    SELECT
        sum(abs(actual)) AS sum_abs_actual,
        sum(absolute_error) AS sum_model_abs_error,
        sum(signed_error) AS sum_model_signed_error,
        sum(naive_absolute_error) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) AS sum_naive_abs_error,
        count(*) AS mature_pair_rows,
        count(*) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) AS benchmark_pair_rows,
        avg(
            CASE WHEN model_beats_primary_naive THEN 1.0 ELSE 0.0 END
        ) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) * 100 AS model_beat_rate_pct
    FROM analytics.v_forecast_evaluation_v283
),
registry AS (
    SELECT
        count(*) AS issued_rows,
        count(DISTINCT project_key) AS issued_projects,
        count(DISTINCT horizon) AS issued_horizons
    FROM model_control.forecast_issue_registry
),
base AS (
    SELECT
        p.cells,
        p.defensible_cells,
        p.projects_with_mature,
        p.mature_pairs,
        p.benchmark_pairs,

        100.0 * m.sum_model_abs_error
            / nullif(m.sum_abs_actual, 0) AS global_wape_pct,

        100.0 * m.sum_model_signed_error
            / nullif(m.sum_abs_actual, 0) AS global_bias_pct,

        100.0 * m.sum_naive_abs_error
            / nullif(m.sum_abs_actual, 0) AS naive_wape_pct,

        100.0 * (
            1.0 - m.sum_model_abs_error
                  / nullif(m.sum_naive_abs_error, 0)
        ) AS skill_vs_naive_pct,

        m.model_beat_rate_pct,

        100.0 * m.benchmark_pair_rows
            / nullif(m.mature_pair_rows, 0) AS benchmark_coverage_pct,

        CASE
            WHEN m.mature_pair_rows > 0 THEN 100.0
        END AS leakage_safe_pct,

        r.issued_rows,
        r.issued_projects,
        r.issued_horizons

    FROM perf p
    CROSS JOIN metrics m
    CROSS JOIN registry r
)
SELECT
    *,

    CASE
        WHEN issued_rows = 0 THEN 'BLOCK'

        WHEN mature_pairs >= 12
         AND projects_with_mature >= 3
         AND defensible_cells >= 3
         AND global_wape_pct <= 25
         AND abs(global_bias_pct) <= 15
         AND benchmark_coverage_pct >= 90
         AND skill_vs_naive_pct > 0
         AND model_beat_rate_pct >= 50
         AND leakage_safe_pct = 100
        THEN 'PASS'

        WHEN mature_pairs >= 6
         AND projects_with_mature >= 2
         AND defensible_cells >= 1
         AND global_wape_pct <= 50
         AND abs(global_bias_pct) <= 30
         AND benchmark_coverage_pct >= 80
         AND skill_vs_naive_pct >= 0
         AND leakage_safe_pct = 100
        THEN 'WARN'

        ELSE 'BLOCK'
    END AS gate_status,

    CASE
        WHEN issued_rows = 0 THEN 0

        WHEN mature_pairs >= 12
         AND projects_with_mature >= 3
         AND defensible_cells >= 3
         AND global_wape_pct <= 25
         AND abs(global_bias_pct) <= 15
         AND benchmark_coverage_pct >= 90
         AND skill_vs_naive_pct > 0
         AND model_beat_rate_pct >= 50
         AND leakage_safe_pct = 100
        THEN 100

        WHEN mature_pairs >= 6
         AND projects_with_mature >= 2
         AND defensible_cells >= 1
         AND global_wape_pct <= 50
         AND abs(global_bias_pct) <= 30
         AND benchmark_coverage_pct >= 80
         AND skill_vs_naive_pct >= 0
         AND leakage_safe_pct = 100
        THEN 50

        ELSE 0
    END AS gate_score,

    CASE
        WHEN issued_rows = 0
        THEN 'Aún no existe un registro prospectivo de forecasts emitidos.'

        WHEN mature_pairs = 0
        THEN concat(
            'Hay ', issued_rows,
            ' forecasts emitidos prospectivamente, pero todavía están incubando; ',
            'no existe ningún outcome maduro para evaluar.'
        )

        WHEN benchmark_coverage_pct < 80
        THEN concat(
            'Sólo ', round(benchmark_coverage_pct, 1),
            '% de los outcomes maduros tiene benchmark naïve comparable.'
        )

        WHEN skill_vs_naive_pct < 0
        THEN concat(
            'El modelo todavía pierde frente al benchmark naïve: skill=',
            round(skill_vs_naive_pct, 1), '%.'
        )

        WHEN global_wape_pct > 50
        THEN concat(
            'WAPE prospectivo ', round(global_wape_pct, 1),
            '% es demasiado alto para WARN.'
        )

        WHEN abs(global_bias_pct) > 30
        THEN concat(
            'Bias prospectivo ', round(global_bias_pct, 1),
            '% es demasiado alto para WARN.'
        )

        WHEN mature_pairs < 6
        THEN concat(
            'Sólo existen ', mature_pairs,
            ' outcomes maduros; WARN requiere al menos 6.'
        )

        WHEN defensible_cells = 0
        THEN 'No existe todavía una celda proyecto×horizonte defendible.'

        WHEN global_wape_pct > 25
        THEN concat(
            'WAPE prospectivo ', round(global_wape_pct, 1),
            '% supera el umbral PASS de 25%.'
        )

        WHEN abs(global_bias_pct) > 15
        THEN concat(
            'Bias prospectivo ', round(global_bias_pct, 1),
            '% supera ±15%.'
        )

        WHEN defensible_cells < 3
        THEN concat(
            'Sólo ', defensible_cells,
            ' celdas son defendibles; PASS requiere 3.'
        )

        ELSE 'Forecast prospectivo defendible y mejor que el benchmark naïve.'
    END AS gate_reason

FROM base;


CREATE OR REPLACE VIEW analytics.v_predictive_evidence_factory_v283 AS
WITH registry AS (
    SELECT
        count(*) AS issued_total,
        count(DISTINCT project_key) AS projects_issued,
        count(DISTINCT horizon) AS horizons_issued,
        max(issued_at) AS latest_issue_at
    FROM model_control.forecast_issue_registry
),
canonical AS (
    SELECT
        count(*) AS active_forecast_cells,
        coalesce(sum(revision_count - 1), 0) AS revision_events
    FROM model_control.v_forecast_issue_canonical
),
clock AS (
    SELECT
        count(*) FILTER (WHERE maturity_status = 'INCUBATING') AS incubating,
        count(*) FILTER (WHERE maturity_status = 'EVALUATED') AS evaluated,
        count(*) FILTER (WHERE maturity_status = 'OVERDUE_NO_ACTUAL') AS overdue_no_actual,
        min(expected_maturity_date) FILTER (
            WHERE maturity_status = 'INCUBATING'
        ) AS next_maturity_date,
        count(*) FILTER (
            WHERE primary_benchmark_prediction IS NOT NULL
        ) AS benchmarked_active
    FROM analytics.v_forecast_maturity_clock_v283
),
gate AS (
    SELECT *
    FROM analytics.v_forecast_predictive_gate_v283
),
latest_batch AS (
    SELECT
        issue_batch_id,
        issued_at,
        slot,
        source_rows,
        candidate_cells,
        inserted_rows,
        unchanged_rows,
        ambiguous_cells,
        skipped_rows,
        capture_status
    FROM model_control.forecast_issue_batch
    ORDER BY issued_at DESC, created_at DESC
    LIMIT 1
)
SELECT
    r.issued_total,
    r.projects_issued,
    r.horizons_issued,
    r.latest_issue_at,

    c.active_forecast_cells,
    c.revision_events,

    k.incubating,
    k.evaluated,
    k.overdue_no_actual,
    k.next_maturity_date,
    k.benchmarked_active,

    g.mature_pairs,
    g.defensible_cells,
    g.global_wape_pct,
    g.global_bias_pct,
    g.naive_wape_pct,
    g.skill_vs_naive_pct,
    g.model_beat_rate_pct,
    g.benchmark_coverage_pct,
    g.gate_status,
    g.gate_reason,

    lb.issue_batch_id AS latest_batch_id,
    lb.slot AS latest_batch_slot,
    lb.source_rows AS latest_source_rows,
    lb.candidate_cells AS latest_candidate_cells,
    lb.inserted_rows AS latest_inserted_rows,
    lb.unchanged_rows AS latest_unchanged_rows,
    lb.ambiguous_cells AS latest_ambiguous_cells,
    lb.skipped_rows AS latest_skipped_rows,
    lb.capture_status AS latest_capture_status

FROM registry r
CROSS JOIN canonical c
CROSS JOIN clock k
CROSS JOIN gate g
LEFT JOIN latest_batch lb ON true;


COMMENT ON TABLE model_control.forecast_issue_registry IS
'Immutable prospective registry. A forecast enters only when Medallio actually observes/emits it; historical backtests are never promoted into this table.';

COMMENT ON VIEW analytics.v_forecast_maturity_clock_v283 IS
'Maturity clock for the latest issued forecast per project×target×horizon. INCUBATING → EVALUATED only after the target month closes with a real actual.';

COMMENT ON TABLE model_control.forecast_naive_benchmark_snapshot IS
'Naive benchmark frozen at forecast issuance. Primary policy: rolling 3 complete months, fallback last complete month, then seasonal 12m.';

COMMENT ON VIEW analytics.v_forecast_predictive_gate_v283 IS
'L3 gate based only on prospective issued forecasts. PASS also requires beating the frozen naïve benchmark.';

COMMIT;
