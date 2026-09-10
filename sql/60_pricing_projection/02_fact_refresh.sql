-- Deterministic monthly pricing scenario fact.
-- Preserves the original M semantics while moving execution into PostgreSQL.

CREATE TABLE IF NOT EXISTS analytics.fact_proyeccion_pricing (
    proyecto                       text NOT NULL,
    tipo_unidad                    text NOT NULL,
    nombre_tipologia               text NOT NULL,
    tipologia_ubicacion            integer NOT NULL,
    "ClaveTipologia"               text NOT NULL,
    "ClaveTipologiaUbicacion"      text NOT NULL,
    escenario                      text NOT NULL,
    fecha_periodo                  date NOT NULL,
    mes_n                          integer NOT NULL,
    stock_total_inicial            numeric NOT NULL,
    stock_inicial                  numeric NOT NULL,
    ventas_mes_base                numeric NOT NULL,
    factor_tramo                   numeric NOT NULL,
    ventas_proyectadas_mes         numeric NOT NULL,
    stock_final                    numeric NOT NULL,
    ventas_acumuladas              numeric NOT NULL,
    pct_vendido_acumulado          numeric NOT NULL,
    precio_m2_base                 numeric NOT NULL,
    area_total_promedio            numeric NOT NULL,
    descuento_promedio             numeric NOT NULL,
    precio_unitario_base           numeric NOT NULL,
    revenue_base_tipologia         numeric NOT NULL,
    aumento_acumulado_usd_m2       numeric NOT NULL,
    precio_m2_vigente              numeric NOT NULL,
    precio_unitario_proyectado     numeric NOT NULL,
    ingreso_mes                    numeric NOT NULL,
    ingreso_acumulado              numeric NOT NULL,
    flag_hito_1_activado           integer NOT NULL,
    flag_hito_2_activado           integer NOT NULL,
    flag_hito_3_activado           integer NOT NULL,
    flag_hito_4_activado           integer NOT NULL,
    flag_stockout                  integer NOT NULL,
    modelo_version                 text NOT NULL DEFAULT 'pricing_projection_v1',
    refreshed_at                   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (
        proyecto, tipo_unidad, nombre_tipologia, tipologia_ubicacion, escenario, mes_n
    )
);

COMMENT ON TABLE analytics.fact_proyeccion_pricing IS
'Simulación determinística mensual de stock, pricing e ingreso por tipología y escenario. No es forecast estadístico ni evidencia causal.';
COMMENT ON COLUMN analytics.fact_proyeccion_pricing.flag_hito_4_activado IS
'El M original calculaba este flag pero lo omitía en el último Expand. Medallio lo conserva explícitamente.';

CREATE OR REPLACE PROCEDURE pricing.refresh_fact_proyeccion_pricing()
LANGUAGE plpgsql
AS $$
DECLARE
    b record;
    s record;
    v_mes integer;
    v_stock_ini numeric;
    v_stock_fin numeric;
    v_factor numeric;
    v_ventas_teoricas numeric;
    v_ventas_mes numeric;
    v_ventas_acum numeric;
    v_pct_vendido numeric;
    v_aumento numeric;
    v_precio_m2 numeric;
    v_precio_unitario numeric;
    v_ingreso_mes numeric;
    v_ingreso_acum numeric;
    v_h1 integer;
    v_h2 integer;
    v_h3 integer;
    v_h4 integer;
BEGIN
    TRUNCATE TABLE analytics.fact_proyeccion_pricing;

    FOR b IN
        SELECT *
        FROM analytics.v_base_proyeccion_tipologia
        ORDER BY proyecto, tipo_unidad, nombre_tipologia, tipologia_ubicacion
    LOOP
        FOR s IN
            SELECT DISTINCT escenario
            FROM pricing.absorption_scenario
            WHERE activo
            ORDER BY escenario
        LOOP
            v_stock_ini := b.stock_total_inicial;
            v_ventas_acum := 0;
            v_ingreso_acum := 0;

            FOR v_mes IN 1..b.meta_meses
            LOOP
                SELECT COALESCE((
                    SELECT a.factor_ventas
                    FROM pricing.absorption_scenario a
                    WHERE a.activo
                      AND a.escenario = s.escenario
                      AND v_mes BETWEEN a.mes_inicio AND a.mes_fin
                    ORDER BY a.tramo
                    LIMIT 1
                ), 1)
                INTO v_factor;

                v_ventas_teoricas := b.ventas_mes_base * v_factor;
                v_ventas_mes := CASE
                    WHEN v_stock_ini <= 0 THEN 0
                    ELSE LEAST(v_stock_ini, v_ventas_teoricas)
                END;
                v_stock_fin := GREATEST(0, v_stock_ini - v_ventas_mes);
                v_ventas_acum := v_ventas_acum + v_ventas_mes;
                v_pct_vendido := CASE
                    WHEN b.stock_total_inicial = 0 THEN 0
                    ELSE v_ventas_acum / b.stock_total_inicial
                END;

                SELECT
                    COALESCE(SUM(h.aumento_usd_m2), 0),
                    COALESCE(MAX(CASE WHEN h.hito = 1 THEN 1 ELSE 0 END), 0),
                    COALESCE(MAX(CASE WHEN h.hito = 2 THEN 1 ELSE 0 END), 0),
                    COALESCE(MAX(CASE WHEN h.hito = 3 THEN 1 ELSE 0 END), 0),
                    COALESCE(MAX(CASE WHEN h.hito = 4 THEN 1 ELSE 0 END), 0)
                INTO v_aumento, v_h1, v_h2, v_h3, v_h4
                FROM pricing.price_milestone h
                WHERE h.activo
                  AND h.proyecto = b.proyecto
                  AND h.tipo_unidad = b.tipo_unidad
                  AND h.nombre_tipologia = b.nombre_tipologia
                  AND (
                      v_mes >= h.mes_hito
                      OR v_pct_vendido >= h.pct_vendido_objetivo
                  );

                v_precio_m2 := b.precio_m2_base + v_aumento;
                v_precio_unitario :=
                    v_precio_m2 * b.area_total_promedio * (1 - b.descuento_promedio);
                v_ingreso_mes := v_ventas_mes * v_precio_unitario;
                v_ingreso_acum := v_ingreso_acum + v_ingreso_mes;

                INSERT INTO analytics.fact_proyeccion_pricing (
                    proyecto, tipo_unidad, nombre_tipologia, tipologia_ubicacion,
                    "ClaveTipologia", "ClaveTipologiaUbicacion",
                    escenario, fecha_periodo, mes_n,
                    stock_total_inicial, stock_inicial, ventas_mes_base,
                    factor_tramo, ventas_proyectadas_mes, stock_final,
                    ventas_acumuladas, pct_vendido_acumulado,
                    precio_m2_base, area_total_promedio, descuento_promedio,
                    precio_unitario_base, revenue_base_tipologia,
                    aumento_acumulado_usd_m2, precio_m2_vigente,
                    precio_unitario_proyectado, ingreso_mes, ingreso_acumulado,
                    flag_hito_1_activado, flag_hito_2_activado,
                    flag_hito_3_activado, flag_hito_4_activado, flag_stockout,
                    modelo_version, refreshed_at
                )
                VALUES (
                    b.proyecto, b.tipo_unidad, b.nombre_tipologia, b.tipologia_ubicacion,
                    b."ClaveTipologia", b."ClaveTipologiaUbicacion",
                    s.escenario,
                    (b.fecha_inicio + make_interval(months => v_mes - 1))::date,
                    v_mes,
                    b.stock_total_inicial, v_stock_ini, b.ventas_mes_base,
                    v_factor, v_ventas_mes, v_stock_fin,
                    v_ventas_acum, v_pct_vendido,
                    b.precio_m2_base, b.area_total_promedio, b.descuento_promedio,
                    b.precio_unitario_base, b.revenue_base_tipologia,
                    v_aumento, v_precio_m2, v_precio_unitario,
                    v_ingreso_mes, v_ingreso_acum,
                    v_h1, v_h2, v_h3, v_h4,
                    CASE WHEN v_stock_fin <= 0 THEN 1 ELSE 0 END,
                    'pricing_projection_v1', now()
                );

                v_stock_ini := v_stock_fin;
            END LOOP;
        END LOOP;
    END LOOP;
END;
$$;
