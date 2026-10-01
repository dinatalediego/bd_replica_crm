-- QA contract for pricing projection.

CREATE OR REPLACE VIEW pricing.v_projection_health AS
WITH active_scenarios AS (
    SELECT DISTINCT escenario
    FROM pricing.absorption_scenario
    WHERE activo
),
expected AS (
    SELECT
        COALESCE(SUM(b.meta_meses), 0)::bigint
        * (SELECT COUNT(*) FROM active_scenarios)::bigint AS expected_rows
    FROM pricing.projection_baseline_assumption b
    WHERE b.activo
),
coverage AS (
    SELECT COUNT(*)::bigint AS coverage_errors
    FROM pricing.projection_baseline_assumption b
    CROSS JOIN active_scenarios s
    CROSS JOIN LATERAL generate_series(1, b.meta_meses) g(mes_n)
    WHERE b.activo
      AND (
          SELECT COUNT(*)
          FROM pricing.absorption_scenario a
          WHERE a.activo
            AND a.escenario = s.escenario
            AND g.mes_n BETWEEN a.mes_inicio AND a.mes_fin
      ) <> 1
),
duplicates AS (
    SELECT COUNT(*)::bigint AS duplicate_grains
    FROM (
        SELECT
            proyecto, tipo_unidad, nombre_tipologia,
            tipologia_ubicacion, escenario, mes_n
        FROM analytics.fact_proyeccion_pricing
        GROUP BY
            proyecto, tipo_unidad, nombre_tipologia,
            tipologia_ubicacion, escenario, mes_n
        HAVING COUNT(*) > 1
    ) x
),
invalid AS (
    SELECT COUNT(*)::bigint AS invalid_rows
    FROM analytics.fact_proyeccion_pricing
    WHERE stock_inicial < 0
       OR stock_final < 0
       OR ventas_proyectadas_mes < 0
       OR ventas_proyectadas_mes > stock_inicial
       OR pct_vendido_acumulado < 0
       OR pct_vendido_acumulado > 1
       OR ingreso_acumulado < ingreso_mes
)
SELECT
    (SELECT COUNT(*) FROM pricing.projection_baseline_assumption WHERE activo)::bigint
        AS baselines_activos,
    (SELECT COUNT(*) FROM active_scenarios)::bigint AS escenarios_activos,
    (SELECT COUNT(*) FROM pricing.price_milestone WHERE activo)::bigint AS hitos_activos,
    (SELECT expected_rows FROM expected) AS filas_esperadas,
    (SELECT COUNT(*) FROM analytics.fact_proyeccion_pricing)::bigint AS filas_fact,
    (SELECT coverage_errors FROM coverage) AS errores_cobertura_escenario,
    (SELECT duplicate_grains FROM duplicates) AS granos_duplicados,
    (SELECT invalid_rows FROM invalid) AS filas_invalidas,
    (SELECT MAX(refreshed_at) FROM analytics.fact_proyeccion_pricing) AS ultimo_refresh;

COMMENT ON VIEW pricing.v_projection_health IS
'QA del simulador: cobertura exacta de escenarios, cardinalidad esperada, granularidad e invariantes de stock.';
