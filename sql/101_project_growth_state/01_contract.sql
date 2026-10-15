-- Medallio v2.7.2
-- Estado comparable real por proyecto + cola de acciones ejecutivas.
-- No inventa uplift causal, ROI ni Value to Capture.
-- Depende de:
--   analytics.comercial_proyecto_mes
--   analytics.v_absorcion_ventas_mensual
--   analytics.v_commercial_forecast_current / performance
--   decision_intelligence.v_ml_impact_baseline
--
-- La vista separa:
--   1) operación física real (stock/ventas/absorción),
--   2) forecast emitido y error maduro,
--   3) planeamiento económico importado,
--   4) recomendación D1, sin promover causalidad.

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE OR REPLACE VIEW analytics.v_project_growth_state AS
WITH latest_any AS (
    SELECT *
    FROM (
        SELECT
            p.*,
            row_number() OVER (
                PARTITION BY p.codigo_proyecto
                ORDER BY p.periodo_mes DESC
            ) AS rn
        FROM analytics.comercial_proyecto_mes p
    ) x
    WHERE rn = 1
),
latest_complete AS (
    SELECT *
    FROM (
        SELECT
            p.*,
            row_number() OVER (
                PARTITION BY p.codigo_proyecto
                ORDER BY p.periodo_mes DESC
            ) AS rn
        FROM analytics.comercial_proyecto_mes p
        WHERE NOT p.mes_parcial
    ) x
    WHERE rn = 1
),
rolling AS (
    SELECT
        p.codigo_proyecto,
        avg(p.ventas_mes::numeric)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '3 months'
            ) AS ventas_promedio_3m,
        avg(p.ventas_mes::numeric)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '6 months'
            ) AS ventas_promedio_6m,
        avg(p.absorcion_mes)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '3 months'
            ) AS absorcion_promedio_3m,
        avg(p.absorcion_mes)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '6 months'
            ) AS absorcion_promedio_6m,
        sum(p.ventas_mes)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '3 months'
            ) AS ventas_3m,
        sum(p.ventas_mes)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '6 months'
            ) AS ventas_6m,
        count(*)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '3 months'
            ) AS meses_completos_3m,
        count(*)
            FILTER (
                WHERE NOT p.mes_parcial
                  AND p.periodo_mes >= date_trunc(
                      'month',
                      (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
                  )::date - interval '6 months'
            ) AS meses_completos_6m
    FROM analytics.comercial_proyecto_mes p
    GROUP BY p.codigo_proyecto
),
forecast_h1 AS (
    SELECT DISTINCT ON (f.project)
        f.project AS codigo_proyecto,
        f.run_id AS forecast_run_id,
        f.origin AS forecast_origin,
        f.horizon AS forecast_horizon,
        f.prediction AS forecast_units_h1,
        f.stock AS forecast_stock_base,
        f.stock_remaining AS forecast_stock_remaining,
        f.target_sales AS forecast_target_sales,
        f.expected_shortfall AS forecast_shortfall_units,
        f.recommendation AS forecast_recommendation,
        f.evidence_level AS forecast_evidence_level,
        f.created_at AS forecast_created_at
    FROM analytics.v_commercial_forecast_current f
    WHERE f.is_selected
      AND f.horizon = 1
    ORDER BY f.project, f.created_at DESC, f.run_id DESC
),
forecast_perf AS (
    SELECT
        p.project AS codigo_proyecto,
        count(*) FILTER (
            WHERE p.is_selected
              AND p.eligible_for_operational_scoring
              AND p.actual IS NOT NULL
        ) AS forecast_outcomes_maduros,
        100 * sum(p.absolute_error) FILTER (
            WHERE p.is_selected
              AND p.eligible_for_operational_scoring
              AND p.actual IS NOT NULL
        )
        / nullif(
            sum(abs(p.actual)) FILTER (
                WHERE p.is_selected
                  AND p.eligible_for_operational_scoring
                  AND p.actual IS NOT NULL
            ),
            0
        ) AS forecast_wape_pct,
        100 * sum(p.error) FILTER (
            WHERE p.is_selected
              AND p.eligible_for_operational_scoring
              AND p.actual IS NOT NULL
        )
        / nullif(
            sum(abs(p.actual)) FILTER (
                WHERE p.is_selected
                  AND p.eligible_for_operational_scoring
                  AND p.actual IS NOT NULL
            ),
            0
        ) AS forecast_bias_pct,
        max(p.measured_at) FILTER (
            WHERE p.is_selected
              AND p.eligible_for_operational_scoring
        ) AS forecast_ultimo_outcome
    FROM analytics.v_commercial_forecast_performance p
    GROUP BY p.project
),
latest_impact_snapshot AS (
    SELECT s.snapshot_id, s.as_of_date, s.imported_at
    FROM decision_intelligence.ml_impact_snapshot s
    ORDER BY s.as_of_date DESC, s.imported_at DESC, s.snapshot_id DESC
    LIMIT 1
),
economics AS (
    SELECT
        b.codigo_proyecto,
        b.nombre_proyecto,
        b.as_of_date AS economics_as_of_date,
        b.meta_soles,
        b.colocado_soles,
        b.gap_matematico_soles AS gap_meta_soles,
        b.gap_reportado_soles,
        b.stock_remanente_soles,
        b.stock_disponible_soles,
        b.stock_bloqueado_soles,
        b.unidades_totales,
        b.unidades_remanentes,
        b.unidades_disponibles,
        b.unidades_bloqueadas,
        b.cumplimiento_actual,
        b.conciliacion AS economics_conciliacion
    FROM decision_intelligence.v_ml_impact_baseline b
    JOIN latest_impact_snapshot s
      ON s.snapshot_id = b.snapshot_id
),
base AS (
    SELECT
        a.codigo_proyecto AS project_key,
        coalesce(a.nombre_proyecto, e.nombre_proyecto, a.codigo_proyecto) AS project_name,

        -- Corte y comparabilidad temporal.
        a.fecha_corte AS snapshot_date,
        a.periodo_mes AS current_period,
        a.mes_parcial AS current_period_partial,
        c.periodo_mes AS latest_complete_period,
        a.mes_vida,
        a.mes_calendario,

        -- Estado físico.
        a.stock_lanzamiento,
        a.stock_inicial AS current_stock_open,
        a.ventas_mes AS current_sales_units,
        a.ventas_acumuladas,
        a.stock_final AS stock_units,
        a.absorcion_mes AS current_absorption_rate,
        a.absorcion_acumulada,
        a.ventas_por_30_dias_unidad AS current_sales_per_30_exposure_days,
        a.unidades_revision,

        -- Último mes completo.
        c.stock_inicial AS last_complete_stock_open,
        c.ventas_mes AS last_complete_sales_units,
        c.stock_final AS last_complete_stock_units,
        c.absorcion_mes AS last_complete_absorption_rate,
        c.ventas_por_30_dias_unidad AS last_complete_sales_per_30_exposure_days,

        -- Ritmo comparable, excluyendo el mes parcial.
        r.ventas_promedio_3m,
        r.ventas_promedio_6m,
        r.absorcion_promedio_3m,
        r.absorcion_promedio_6m,
        r.ventas_3m,
        r.ventas_6m,
        r.meses_completos_3m,
        r.meses_completos_6m,
        CASE
            WHEN r.ventas_promedio_3m > 0
            THEN a.stock_final::numeric / r.ventas_promedio_3m
        END AS months_to_zero,

        -- Forecast emitido + evidencia madura.
        f.forecast_run_id,
        f.forecast_origin,
        f.forecast_units_h1,
        f.forecast_stock_base,
        f.forecast_stock_remaining,
        f.forecast_target_sales,
        f.forecast_shortfall_units,
        f.forecast_recommendation,
        f.forecast_evidence_level,
        f.forecast_created_at,
        fp.forecast_outcomes_maduros,
        fp.forecast_wape_pct,
        fp.forecast_bias_pct,
        fp.forecast_ultimo_outcome,

        -- Planeamiento económico importado: no confundir con causalidad.
        e.economics_as_of_date,
        e.meta_soles AS target_value,
        e.colocado_soles AS commercial_placed_value,
        e.gap_meta_soles AS gap_value,
        e.gap_reportado_soles,
        e.stock_remanente_soles AS stock_value,
        e.stock_disponible_soles,
        e.stock_bloqueado_soles,
        e.cumplimiento_actual,
        e.economics_conciliacion,

        -- Aliases del contrato de Evidence & Outcome.
        c.ventas_mes::numeric AS sales_units,
        NULL::numeric AS sales_value,
        r.absorcion_promedio_3m AS absorption_rate,
        f.forecast_units_h1 AS forecast_units,

        -- Deliberadamente NULL hasta que una decisión tenga evidencia económica real.
        NULL::numeric AS value_to_capture,
        NULL::numeric AS action_cost,
        NULL::numeric AS uplift_pct,
        NULL::numeric AS confidence,
        NULL::numeric AS expected_roi,

        CASE
            WHEN a.unidades_revision > 0 THEN 'WARN'
            WHEN e.economics_conciliacion = 'REVISAR' THEN 'WARN'
            ELSE 'PASS'
        END AS data_quality_status,

        concat_ws(
            '; ',
            CASE WHEN a.unidades_revision > 0
                THEN format('%s unidades requieren revisión', a.unidades_revision) END,
            CASE WHEN e.economics_conciliacion = 'REVISAR'
                THEN 'planeamiento económico requiere conciliación' END,
            CASE WHEN fp.forecast_wape_pct IS NULL
                THEN 'forecast sin WAPE maduro por proyecto' END
        ) AS evidence_gaps,

        'analytics.v_project_growth_state'::text AS source_artifact
    FROM latest_any a
    LEFT JOIN latest_complete c USING (codigo_proyecto)
    LEFT JOIN rolling r USING (codigo_proyecto)
    LEFT JOIN forecast_h1 f USING (codigo_proyecto)
    LEFT JOIN forecast_perf fp USING (codigo_proyecto)
    LEFT JOIN economics e USING (codigo_proyecto)
)
SELECT
    base.*,
    (
        CASE
            WHEN base.target_value > 0 AND base.gap_value / base.target_value >= 0.25 THEN 30
            WHEN base.target_value > 0 AND base.gap_value / base.target_value >= 0.10 THEN 20
            WHEN base.gap_value > 0 THEN 10
            ELSE 0
        END
        +
        CASE
            WHEN base.months_to_zero > 18 THEN 25
            WHEN base.months_to_zero > 12 THEN 15
            WHEN base.months_to_zero > 6 THEN 5
            ELSE 0
        END
        +
        CASE WHEN coalesce(base.forecast_shortfall_units, 0) > 0 THEN 20 ELSE 0 END
        +
        CASE WHEN coalesce(base.unidades_revision, 0) > 0 THEN 15 ELSE 0 END
        +
        CASE WHEN base.economics_conciliacion = 'REVISAR' THEN 10 ELSE 0 END
    )::integer AS attention_score,
    CASE
        WHEN coalesce(base.unidades_revision, 0) > 0
            THEN 'Resolver calidad de stock/ventas antes de intervenir comercialmente.'
        WHEN base.economics_conciliacion = 'REVISAR'
            THEN 'Conciliar meta, colocado y stock antes de usar el valor económico para decidir.'
        WHEN coalesce(base.gap_value, 0) > 0
             AND coalesce(base.months_to_zero, 0) > 18
            THEN 'Diseñar intervención de pricing/comercial para acelerar absorción y medir baseline, costo, outcome y ROI.'
        WHEN coalesce(base.forecast_shortfall_units, 0) > 0
            THEN 'Revisar plan comercial frente al forecast y registrar owner, acción, costo y outcome.'
        WHEN coalesce(base.gap_value, 0) > 0
            THEN 'Priorizar plan para cerrar el gap a meta y cuantificar Value to Capture antes de escalar.'
        ELSE 'Mantener rumbo y exigir evidencia de valor.'
    END AS suggested_action,
    CASE
        WHEN coalesce(base.unidades_revision, 0) > 0
            THEN 'BI + Operaciones'
        WHEN base.economics_conciliacion = 'REVISAR'
            THEN 'BI + Finanzas'
        WHEN coalesce(base.gap_value, 0) > 0
             AND coalesce(base.months_to_zero, 0) > 18
            THEN 'Comercial + Pricing'
        WHEN coalesce(base.forecast_shortfall_units, 0) > 0
            THEN 'Comercial + BI'
        WHEN coalesce(base.gap_value, 0) > 0
            THEN 'Comercial'
        ELSE 'AI Steering Committee'
    END AS suggested_owner,
    CASE
        WHEN coalesce(base.unidades_revision, 0) > 0 THEN 'AHORA'
        WHEN (
            CASE
                WHEN base.target_value > 0 AND base.gap_value / base.target_value >= 0.25 THEN 30
                WHEN base.target_value > 0 AND base.gap_value / base.target_value >= 0.10 THEN 20
                WHEN base.gap_value > 0 THEN 10
                ELSE 0
            END
            +
            CASE
                WHEN base.months_to_zero > 18 THEN 25
                WHEN base.months_to_zero > 12 THEN 15
                WHEN base.months_to_zero > 6 THEN 5
                ELSE 0
            END
            +
            CASE WHEN coalesce(base.forecast_shortfall_units, 0) > 0 THEN 20 ELSE 0 END
        ) >= 40 THEN 'PRÓXIMO COMITÉ'
        ELSE 'SEGUIMIENTO'
    END AS suggested_urgency,
    true AS outcome_required,
    true AS roi_required,
    CASE
        WHEN coalesce(base.unidades_revision, 0) > 0
            THEN 'unidades_revision → 0'
        WHEN coalesce(base.gap_value, 0) > 0
             AND coalesce(base.months_to_zero, 0) > 18
            THEN 'absorcion_promedio_3m, months_to_zero, gap_value'
        WHEN coalesce(base.forecast_shortfall_units, 0) > 0
            THEN 'ventas_mes vs forecast_h1 y gap_value'
        WHEN coalesce(base.gap_value, 0) > 0
            THEN 'gap_value y cumplimiento_actual'
        ELSE 'outcome y ROI de la siguiente decisión material'
    END AS suggested_outcome_metric
FROM base;


CREATE OR REPLACE VIEW decision_intelligence.v_project_growth_actions AS
SELECT
    project_key,
    project_name,
    attention_score,
    suggested_action AS decision,
    suggested_owner AS owner,
    suggested_urgency AS urgency,
    CASE
        WHEN gap_value > 0 THEN gap_value
        WHEN stock_value > 0 THEN stock_value
    END AS value_at_stake_soles,
    CASE
        WHEN gap_value > 0 THEN 'GAP_TO_TARGET'
        WHEN stock_value > 0 THEN 'STOCK_EXPOSURE'
        ELSE 'UNQUANTIFIED'
    END AS value_at_stake_type,
    CASE
        WHEN forecast_wape_pct IS NOT NULL AND data_quality_status = 'PASS' THEN 'MEDIA'
        ELSE 'BAJA'
    END AS confidence_label,
    concat_ws(
        '; ',
        CASE WHEN gap_value IS NOT NULL
            THEN format('gap_meta=S/ %s', round(gap_value, 0)) END,
        CASE WHEN months_to_zero IS NOT NULL
            THEN format('meses_stock=%s', round(months_to_zero, 1)) END,
        CASE WHEN forecast_shortfall_units IS NOT NULL
            THEN format('shortfall_h1=%s unidades', round(forecast_shortfall_units, 1)) END,
        CASE WHEN unidades_revision > 0
            THEN format('revision=%s unidades', unidades_revision) END,
        NULLIF(evidence_gaps, '')
    ) AS why,
    suggested_outcome_metric,
    outcome_required,
    roi_required,
    'D1_RECOMMEND'::text AS decision_level,
    snapshot_date,
    latest_complete_period,
    forecast_wape_pct,
    data_quality_status
FROM analytics.v_project_growth_state
ORDER BY attention_score DESC, gap_value DESC NULLS LAST, project_key;


CREATE OR REPLACE FUNCTION decision_intelligence.has_mature_decision_outcomes()
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    has_rows boolean := false;
BEGIN
    IF to_regclass('decision_intelligence.outcome_ledger') IS NULL THEN
        RETURN false;
    END IF;

    EXECUTE $q$
        SELECT EXISTS (
            SELECT 1
            FROM decision_intelligence.outcome_ledger
            WHERE maturity_status = 'MATURE'
        )
    $q$ INTO has_rows;

    RETURN coalesce(has_rows, false);
END;
$$;

CREATE OR REPLACE VIEW decision_intelligence.v_ceo_growth_decision_queue AS
WITH governance AS (
    SELECT
        'PORTFOLIO'::text AS project_key,
        'Portafolio'::text AS project_name,
        100::integer AS attention_score,
        'Hacer obligatorio capturar outcome y ROI de cada decisión asistida por IA.'::text AS decision,
        'AI Steering Committee'::text AS owner,
        'PRÓXIMO COMITÉ'::text AS urgency,
        NULL::numeric AS value_at_stake_soles,
        'GOVERNANCE_GAP'::text AS value_at_stake_type,
        'ALTA'::text AS confidence_label,
        'Sin outcome y ROI no se puede demostrar valor realizado ni aprendizaje causal.'::text AS why,
        'outcome_realizado + ROI_realizado'::text AS suggested_outcome_metric,
        true AS outcome_required,
        true AS roi_required,
        'D1_RECOMMEND'::text AS decision_level,
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date AS snapshot_date,
        NULL::date AS latest_complete_period,
        NULL::numeric AS forecast_wape_pct,
        'PASS'::text AS data_quality_status
    WHERE NOT decision_intelligence.has_mature_decision_outcomes()
),
project_actions AS (
    SELECT *
    FROM decision_intelligence.v_project_growth_actions
    WHERE decision <> 'Mantener rumbo y exigir evidencia de valor.'
)
SELECT * FROM governance
UNION ALL
SELECT * FROM project_actions
UNION ALL
SELECT *
FROM decision_intelligence.v_project_growth_actions
WHERE decision = 'Mantener rumbo y exigir evidencia de valor.'
  AND NOT EXISTS (SELECT 1 FROM governance)
  AND NOT EXISTS (SELECT 1 FROM project_actions)
ORDER BY attention_score DESC, value_at_stake_soles DESC NULLS LAST, project_key;


COMMENT ON VIEW analytics.v_project_growth_state IS
'Estado comparable por proyecto: stock/ventas/absorción reales, rolling sólo de meses completos, forecast con outcomes maduros y planeamiento económico importado. No atribuye causalidad ni inventa ROI.';

COMMENT ON VIEW decision_intelligence.v_project_growth_actions IS
'Recomendaciones D1 derivadas de métricas observables. Requieren outcome y ROI antes de promoción.';

COMMENT ON VIEW decision_intelligence.v_ceo_growth_decision_queue IS
'Cola CEO: prioriza el gate transversal outcome+ROI y luego acciones reales por proyecto.';
