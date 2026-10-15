-- Medallio Temporal Science Factory.
-- Additive/local only: no RAW/CORE mutation, no Redshift access, no rewrite of prior forecast evidence.
CREATE SCHEMA IF NOT EXISTS forecasting_control;
CREATE SCHEMA IF NOT EXISTS forecasting_macro;
CREATE SCHEMA IF NOT EXISTS forecasting_micro;

CREATE TABLE IF NOT EXISTS forecasting_control.temporal_runs (
    run_id text PRIMARY KEY,
    mode text NOT NULL,
    as_of_date date NOT NULL,
    information_cutoff timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('RUNNING','OK','PARTIAL','FAILED')),
    source_semantics text NOT NULL,
    source_fingerprint text,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_temporal_runs_date
    ON forecasting_control.temporal_runs(as_of_date DESC, started_at DESC);

CREATE TABLE IF NOT EXISTS forecasting_control.series_registry (
    series_key text PRIMARY KEY,
    scope text NOT NULL CHECK (scope IN ('MACRO','MICRO')),
    entity_level text NOT NULL,
    entity_id text NOT NULL,
    target_name text NOT NULL,
    frequency text NOT NULL,
    source_relation text NOT NULL,
    hierarchy_path text,
    active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS forecasting_control.variable_profile (
    profile_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES forecasting_control.temporal_runs(run_id),
    series_key text NOT NULL,
    variable_name text NOT NULL,
    variable_role text NOT NULL,
    observed_from date,
    observed_to date,
    observations integer NOT NULL,
    missing_periods integer NOT NULL DEFAULT 0,
    null_rate numeric,
    zero_rate numeric,
    mean_value numeric,
    std_value numeric,
    min_value numeric,
    q05 numeric,
    q25 numeric,
    median numeric,
    q75 numeric,
    q95 numeric,
    max_value numeric,
    skewness numeric,
    kurtosis numeric,
    acf1 numeric,
    acf12 numeric,
    trend_slope numeric,
    seasonal_strength numeric,
    adi numeric,
    cv2 numeric,
    demand_pattern text,
    adf_pvalue numeric,
    kpss_pvalue numeric,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(run_id, series_key, variable_name)
);
CREATE INDEX IF NOT EXISTS ix_variable_profile_series
    ON forecasting_control.variable_profile(series_key, created_at DESC);

CREATE TABLE IF NOT EXISTS forecasting_control.model_suitability (
    suitability_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES forecasting_control.temporal_runs(run_id),
    series_key text NOT NULL,
    model_family text NOT NULL,
    eligible boolean NOT NULL,
    suitability_score numeric NOT NULL CHECK (suitability_score BETWEEN 0 AND 100),
    deployment_role text NOT NULL CHECK (deployment_role IN ('BASELINE','CANDIDATE','SHADOW','NOT_ELIGIBLE')),
    reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    requirements jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(run_id, series_key, model_family)
);

CREATE TABLE IF NOT EXISTS forecasting_control.model_runs (
    model_run_id text PRIMARY KEY,
    temporal_run_id text NOT NULL REFERENCES forecasting_control.temporal_runs(run_id),
    scope text NOT NULL CHECK (scope IN ('MACRO','MICRO')),
    target_name text NOT NULL,
    horizon text NOT NULL,
    model_family text NOT NULL,
    role text NOT NULL CHECK (role IN ('BASELINE','CHALLENGER','CHAMPION','SHADOW')),
    evidence_level text NOT NULL,
    training_start date,
    training_end date,
    validation_start date,
    validation_end date,
    rows_train integer,
    rows_validation integer,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    feature_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
    artifact_path text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS ix_model_runs_scope
    ON forecasting_control.model_runs(scope, target_name, created_at DESC);

CREATE TABLE IF NOT EXISTS forecasting_control.drift_metric (
    drift_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES forecasting_control.temporal_runs(run_id),
    series_key text NOT NULL,
    variable_name text NOT NULL,
    reference_from date,
    reference_to date,
    current_from date,
    current_to date,
    psi numeric,
    mean_shift_std numeric,
    zero_rate_delta numeric,
    status text NOT NULL CHECK (status IN ('OK','WARN','ALERT','INSUFFICIENT_DATA')),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(run_id, series_key, variable_name)
);

CREATE TABLE IF NOT EXISTS forecasting_control.retraining_signal (
    signal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL REFERENCES forecasting_control.temporal_runs(run_id),
    series_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('NO_ACTION','REVIEW','RETRAIN_CANDIDATE','BLOCKED')),
    reason text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(run_id, series_key)
);

CREATE TABLE IF NOT EXISTS forecasting_micro.unit_sale_probability (
    probability_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_run_id text NOT NULL REFERENCES forecasting_control.model_runs(model_run_id),
    codigo_unidad text NOT NULL,
    codigo_proyecto text NOT NULL,
    origin_date date NOT NULL,
    horizon_days integer NOT NULL CHECK (horizon_days IN (30,60,90,180)),
    model_family text NOT NULL,
    probability numeric NOT NULL CHECK (probability BETWEEN 0 AND 1),
    is_selected boolean NOT NULL,
    evidence_level text NOT NULL,
    information_cutoff timestamptz NOT NULL,
    emitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(model_run_id, codigo_unidad, horizon_days)
);
CREATE INDEX IF NOT EXISTS ix_unit_sale_probability_origin
    ON forecasting_micro.unit_sale_probability(codigo_proyecto, origin_date DESC, horizon_days);

-- Reconstructed macro panel. It is diagnostic history, not a point-in-time replay.
CREATE OR REPLACE VIEW forecasting_macro.v_project_month AS
SELECT
    'PROJECT:' || codigo_proyecto AS series_key,
    codigo_proyecto,
    nombre_proyecto,
    periodo_mes,
    mes_vida,
    mes_calendario,
    stock_lanzamiento,
    stock_inicial,
    ventas_mes,
    ventas_acumuladas,
    stock_final,
    absorcion_mes,
    absorcion_acumulada,
    dias_exposicion,
    ventas_por_30_dias_unidad,
    unidades_revision,
    'RECONSTRUCTED_REVISED_HISTORY'::text AS evidence_level,
    false AS point_in_time,
    NULL::timestamptz AS known_at
FROM analytics.comercial_proyecto_mes
WHERE NOT mes_parcial;

CREATE OR REPLACE VIEW forecasting_macro.v_portfolio_month AS
SELECT
    'PORTFOLIO:ALL'::text AS series_key,
    periodo_mes,
    sum(stock_lanzamiento)::bigint AS stock_lanzamiento,
    sum(stock_inicial)::bigint AS stock_inicial,
    sum(ventas_mes)::bigint AS ventas_mes,
    sum(ventas_acumuladas)::bigint AS ventas_acumuladas,
    sum(stock_final)::bigint AS stock_final,
    sum(dias_exposicion)::bigint AS dias_exposicion,
    30 * sum(ventas_mes)::numeric / nullif(sum(dias_exposicion), 0) AS ventas_por_30_dias_unidad,
    sum(unidades_revision)::bigint AS unidades_revision,
    count(*)::integer AS proyectos_activos,
    'RECONSTRUCTED_REVISED_HISTORY'::text AS evidence_level,
    false AS point_in_time,
    NULL::timestamptz AS known_at
FROM analytics.comercial_proyecto_mes
WHERE NOT mes_parcial
GROUP BY periodo_mes;

-- Observed daily macro state built only from snapshots captured at that date.
CREATE OR REPLACE VIEW forecasting_macro.v_project_day_observed AS
SELECT
    'PROJECT:' || codigo_proyecto AS series_key,
    codigo_proyecto,
    fecha_corte,
    max(captured_at) AS known_at,
    count(*)::bigint AS unidades,
    count(*) FILTER (WHERE disponible IS TRUE)::bigint AS stock_disponible,
    count(*) FILTER (WHERE estado = 'VENDIDO')::bigint AS unidades_vendidas_estado,
    count(*) FILTER (WHERE requiere_revision)::bigint AS unidades_revision,
    avg(precio_lista) FILTER (WHERE precio_lista > 0)::numeric AS precio_lista_promedio,
    avg(area_total) FILTER (WHERE area_total > 0)::numeric AS area_promedio,
    'OBSERVED_POINT_IN_TIME'::text AS evidence_level,
    true AS point_in_time
FROM analytics.snapshot_unidad_diario
GROUP BY codigo_proyecto, fecha_corte;

CREATE OR REPLACE VIEW forecasting_micro.v_unit_training AS
SELECT
    d.codigo_unidad,
    d.codigo_proyecto,
    d.fecha_corte,
    d.evidencia,
    d.captured_at AS information_cutoff,
    d.disponible,
    d.pendiente_venta,
    d.horizonte_dias,
    d.ventana_fin,
    d.maduro,
    d.venta_vigente,
    d.elegible_validacion_prospectiva,
    d.features->>'tipologia' AS tipologia,
    nullif(d.features->>'dormitorios','')::numeric AS dormitorios,
    d.features->>'moneda' AS moneda,
    d.features->>'estado_construccion' AS estado_construccion,
    nullif(d.features->>'area_total','')::numeric AS area_total,
    nullif(d.features->>'area_relativa','')::numeric AS area_relativa,
    nullif(d.features->>'precio_m2','')::numeric AS precio_m2,
    nullif(d.features->>'precio_relativo','')::numeric AS precio_relativo,
    nullif(d.features->>'mes_vida','')::numeric AS mes_vida,
    nullif(d.features->>'mes_calendario','')::numeric AS mes_calendario,
    nullif(d.features->'demanda_4_semanas'->>'leads_creados','')::numeric AS leads_4w,
    nullif(d.features->'demanda_4_semanas'->>'proformas','')::numeric AS proformas_4w,
    nullif(d.features->'demanda_4_semanas'->>'interacciones','')::numeric AS interacciones_4w,
    nullif(d.features->'demanda_4_semanas'->>'visitas','')::numeric AS visitas_4w,
    d.calidad
FROM features.v_dataset_unidad_entrenamiento d;

CREATE OR REPLACE VIEW forecasting_micro.v_segment_month AS
SELECT
    codigo_proyecto,
    periodo_mes,
    dormitorios,
    coalesce(nombre_tipologia, 'SIN_TIPOLOGIA') AS nombre_tipologia,
    stock_lanzamiento,
    stock_inicial,
    ventas_mes,
    stock_final,
    absorcion_mes,
    area_media,
    area_relativa_media,
    dias_exposicion,
    unidades_revision,
    'RECONSTRUCTED_REVISED_HISTORY'::text AS evidence_level
FROM analytics.v_comercial_composicion_mes
WHERE NOT mes_parcial;

CREATE OR REPLACE VIEW forecasting_micro.v_unit_sale_evaluation AS
SELECT
    p.*,
    t.maduro,
    t.venta_vigente AS actual,
    CASE WHEN t.maduro AND t.venta_vigente IS NOT NULL
         THEN p.probability - t.venta_vigente::numeric END AS error,
    CASE WHEN t.maduro AND t.venta_vigente IS NOT NULL
         THEN power(p.probability - t.venta_vigente::numeric, 2) END AS brier_component,
    t.elegible_validacion_prospectiva
FROM forecasting_micro.unit_sale_probability p
LEFT JOIN forecasting_micro.v_unit_training t
  ON t.codigo_unidad = p.codigo_unidad
 AND t.fecha_corte = p.origin_date
 AND t.horizonte_dias = p.horizon_days
 AND ((p.evidence_level = 'PROSPECTIVE_OBSERVED' AND t.evidencia = 'OBSERVADO')
   OR (p.evidence_level <> 'PROSPECTIVE_OBSERVED' AND t.evidencia = 'RECONSTRUIDO'));

CREATE OR REPLACE VIEW forecasting_control.v_latest_profiles AS
SELECT DISTINCT ON (series_key, variable_name)
    series_key, variable_name, variable_role, run_id, observed_from, observed_to,
    observations, missing_periods, null_rate, zero_rate, mean_value, std_value,
    q05, q25, median, q75, q95, acf1, acf12, trend_slope, seasonal_strength,
    adi, cv2, demand_pattern, adf_pvalue, kpss_pvalue, metadata, created_at
FROM forecasting_control.variable_profile
ORDER BY series_key, variable_name, created_at DESC, profile_id DESC;

CREATE OR REPLACE VIEW forecasting_control.v_latest_model_suitability AS
SELECT DISTINCT ON (series_key, model_family)
    series_key, model_family, eligible, suitability_score, deployment_role,
    reasons, requirements, run_id, created_at
FROM forecasting_control.model_suitability
ORDER BY series_key, model_family, created_at DESC, suitability_id DESC;

CREATE OR REPLACE VIEW forecasting_control.v_system_status AS
SELECT
    r.run_id,
    r.as_of_date,
    r.started_at,
    r.finished_at,
    r.status,
    r.source_semantics,
    count(DISTINCT p.series_key) AS profiled_series,
    count(DISTINCT m.model_run_id) AS model_runs,
    count(DISTINCT s.series_key) FILTER (WHERE s.status IN ('REVIEW','RETRAIN_CANDIDATE','BLOCKED')) AS series_needing_attention,
    r.detail
FROM forecasting_control.temporal_runs r
LEFT JOIN forecasting_control.variable_profile p USING(run_id)
LEFT JOIN forecasting_control.model_runs m ON m.temporal_run_id = r.run_id
LEFT JOIN forecasting_control.retraining_signal s USING(run_id)
GROUP BY r.run_id;

CREATE OR REPLACE FUNCTION forecasting_control.reject_temporal_evidence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Temporal evidence is append-only; create a new run/version';
END $$;

DO $$
DECLARE rel text;
BEGIN
    FOREACH rel IN ARRAY ARRAY[
        'forecasting_control.variable_profile',
        'forecasting_control.model_suitability',
        'forecasting_control.drift_metric',
        'forecasting_control.retraining_signal',
        'forecasting_micro.unit_sale_probability'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = rel::regclass AND tgname = 'temporal_evidence_append_only'
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER temporal_evidence_append_only BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION forecasting_control.reject_temporal_evidence_mutation()',
                rel
            );
        END IF;
    END LOOP;
END $$;
