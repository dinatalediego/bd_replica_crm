-- Economic Intelligence monthly feature mart.
-- Builds on the governed monthly stock/absorption ledger and keeps provenance explicit.
-- Current project/unit universe and current prices are REFERENCE variables only; they are not back-cast as historical truth.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.econ_macro_monthly (
    periodo_mes date PRIMARY KEY,
    tasa_referencia_bcrp numeric,
    tasa_hipotecaria numeric,
    tc_usd_pen numeric,
    inflacion_yoy numeric,
    actividad_yoy numeric,
    desempleo numeric,
    fuente text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE analytics.econ_macro_monthly IS
'Optional monthly macroeconomic inputs. Empty/null values are valid; notebooks remain functional using endogenous market proxies.';

CREATE OR REPLACE VIEW analytics.v_econ_project_monthly_features AS
WITH unit_ref AS (
    SELECT
        u.codigo_proyecto,
        count(*) FILTER (WHERE lower(coalesce(u.tipo_unidad,'')) LIKE '%departamento%')::bigint AS stock_total_departamentos_actual_ref,
        avg(u.precio_lista_actual) FILTER (WHERE lower(coalesce(u.tipo_unidad,'')) LIKE '%departamento%' AND u.precio_lista_actual IS NOT NULL)::numeric AS precio_lista_prom_actual_ref,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY u.precio_lista_actual)
            FILTER (WHERE lower(coalesce(u.tipo_unidad,'')) LIKE '%departamento%' AND u.precio_lista_actual IS NOT NULL)::numeric AS precio_lista_mediana_actual_ref,
        avg(u.precio_m2_actual) FILTER (WHERE lower(coalesce(u.tipo_unidad,'')) LIKE '%departamento%' AND u.precio_m2_actual IS NOT NULL)::numeric AS precio_m2_prom_actual_ref,
        avg(u.descuento_venta_actual) FILTER (WHERE lower(coalesce(u.tipo_unidad,'')) LIKE '%departamento%' AND u.descuento_venta_actual IS NOT NULL)::numeric AS descuento_prom_actual_ref
    FROM core.dim_unidad u
    GROUP BY u.codigo_proyecto
), base AS (
    SELECT
        m.*,
        p.fecha_inicio_venta AS fecha_inicio_comercial,
        p.estado_construccion,
        p.distrito,
        p.moneda AS moneda_proyecto,
        coalesce(r.stock_total_departamentos_actual_ref,0) AS stock_total_departamentos_actual_ref,
        r.precio_lista_prom_actual_ref,
        r.precio_lista_mediana_actual_ref,
        r.precio_m2_prom_actual_ref,
        r.descuento_prom_actual_ref,
        sum(m.altas_mes) OVER (
            PARTITION BY m.codigo_proyecto
            ORDER BY m.periodo_mes
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint AS altas_acumuladas_ledger,
        first_value(m.stock_inicio_observado) OVER (
            PARTITION BY m.codigo_proyecto
            ORDER BY m.periodo_mes
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        )::bigint AS stock_inicial_observado_ledger
    FROM analytics.v_stock_movimiento_mensual_export m
    LEFT JOIN core.dim_proyecto p
      ON p.codigo_proyecto=m.codigo_proyecto
    LEFT JOIN unit_ref r
      ON r.codigo_proyecto=m.codigo_proyecto
), enriched AS (
    SELECT
        b.*,
        (coalesce(b.stock_inicial_observado_ledger,0) + coalesce(b.altas_acumuladas_ledger,0))::bigint AS stock_ofertado_observado_acum,
        CASE
            WHEN b.stock_total_departamentos_actual_ref > 0
            THEN (coalesce(b.stock_inicial_observado_ledger,0) + coalesce(b.altas_acumuladas_ledger,0))::numeric
                 / b.stock_total_departamentos_actual_ref
        END AS cobertura_oferta_ledger_vs_universo_actual,
        CASE
            WHEN (coalesce(b.stock_inicial_observado_ledger,0) + coalesce(b.altas_acumuladas_ledger,0)) > 0
            THEN ((coalesce(b.stock_inicial_observado_ledger,0) + coalesce(b.altas_acumuladas_ledger,0)) - b.saldo_final_observado)::numeric
                 / (coalesce(b.stock_inicial_observado_ledger,0) + coalesce(b.altas_acumuladas_ledger,0))
        END AS absorcion_stock_acumulada_observada,
        CASE
            WHEN b.fecha_inicio_comercial IS NOT NULL
            THEN (
                (extract(year from age(b.periodo_mes, date_trunc('month', b.fecha_inicio_comercial)::date)) * 12)
                + extract(month from age(b.periodo_mes, date_trunc('month', b.fecha_inicio_comercial)::date))
            )::integer
        END AS edad_comercial_meses,
        lag(b.movimiento_neto_mes,1) OVER (PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes) AS mov_neto_lag1,
        lag(b.movimiento_neto_mes,2) OVER (PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes) AS mov_neto_lag2,
        lag(b.movimiento_neto_mes,3) OVER (PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes) AS mov_neto_lag3,
        lag(b.ventas_minutas_mes,1) OVER (PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes) AS minutas_lag1,
        lag(b.absorcion_neta_mes,1) OVER (PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes) AS absorcion_lag1,
        avg(b.movimiento_neto_mes) OVER (
            PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS mov_neto_ma3,
        avg(b.movimiento_neto_mes) OVER (
            PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ) AS mov_neto_ma6,
        avg(b.absorcion_neta_mes) OVER (
            PARTITION BY b.codigo_proyecto ORDER BY b.periodo_mes ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ) AS absorcion_ma6
    FROM base b
), market AS (
    SELECT
        periodo_mes,
        count(DISTINCT codigo_proyecto)::integer AS proyectos_activos_market,
        sum(stock_inicio_observado)::bigint AS stock_inicio_market,
        sum(altas_mes)::bigint AS altas_market,
        sum(movimiento_neto_mes)::bigint AS demanda_neta_market,
        sum(ventas_minutas_mes)::bigint AS minutas_market,
        sum(saldo_final_observado)::bigint AS saldo_final_market,
        sum(movimiento_neto_mes)::numeric / nullif(sum(stock_inicio_observado),0) AS absorcion_neta_market
    FROM enriched
    GROUP BY periodo_mes
)
SELECT
    e.*,
    mk.proyectos_activos_market,
    mk.stock_inicio_market,
    mk.altas_market,
    mk.demanda_neta_market,
    mk.minutas_market,
    mk.saldo_final_market,
    mk.absorcion_neta_market,
    macro.tasa_referencia_bcrp,
    macro.tasa_hipotecaria,
    macro.tc_usd_pen,
    macro.inflacion_yoy,
    macro.actividad_yoy,
    macro.desempleo,
    extract(month from e.periodo_mes)::integer AS mes_calendario,
    extract(year from e.periodo_mes)::integer AS anio_calendario,
    sin(2*pi()*extract(month from e.periodo_mes)::numeric/12.0) AS season_sin,
    cos(2*pi()*extract(month from e.periodo_mes)::numeric/12.0) AS season_cos
FROM enriched e
LEFT JOIN market mk USING(periodo_mes)
LEFT JOIN analytics.econ_macro_monthly macro USING(periodo_mes);

COMMENT ON VIEW analytics.v_econ_project_monthly_features IS
'Monthly project economic-intelligence mart. Historical flow variables come from governed ledger. stock_total_departamentos_actual_ref and price_*_actual_ref are current reference variables, never historical back-casts.';
