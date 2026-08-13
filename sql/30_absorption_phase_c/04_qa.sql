CREATE OR REPLACE PROCEDURE analytics.run_absorption_phase_c_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
    -------------------------------------------------------------------------
    -- Stock equation.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.fact_stock_ofertado_diario
    WHERE stock_fin <>
          stock_inicio + altas - separaciones + caidas_reingresadas - retiros;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'DAILY_STOCK_EQUATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'equation',
            'stock_fin = stock_inicio + altas - separaciones + caidas_reingresadas - retiros'
        )
    );

    -------------------------------------------------------------------------
    -- No stock negativo.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.fact_stock_ofertado_diario
    WHERE stock_fin < 0 OR separadas_activas < 0 OR vendidas_acumuladas < 0;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'NEGATIVE_DAILY_INVENTORY_STATE',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        '{}'::jsonb
    );

    -------------------------------------------------------------------------
    -- Ventas detalle = agregado mensual.
    -------------------------------------------------------------------------
    WITH detail AS (
        SELECT
            date_trunc('month',fecha_venta)::date periodo_mes,
            codigo_proyecto,
            count(*) ventas
        FROM analytics.fact_ventas_detalle
        GROUP BY 1,2
    )
    SELECT count(*) INTO n
    FROM analytics.agg_ventas_mensual a
    FULL JOIN detail d
      USING(periodo_mes,codigo_proyecto)
    WHERE coalesce(a.ventas,0) <> coalesce(d.ventas,0);

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SALES_DETAIL_MONTHLY_RECONCILIATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        '{}'::jsonb
    );

    -------------------------------------------------------------------------
    -- Ventas canónicas no pueden tener fecha inválida.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.fact_ventas_detalle
    WHERE fecha_venta < fecha_separacion;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'CANONICAL_SALE_BEFORE_SEPARATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        '{}'::jsonb
    );

    -------------------------------------------------------------------------
    -- Movimientos efectivos sin proyecto: visibilidad, no silencio.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.fact_movimientos_stock
    WHERE transition_applied
      AND codigo_proyecto IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'EFFECTIVE_MOVEMENT_WITHOUT_PROJECT',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'impact',
            'Excluded from project-level stock and absorption until project key is resolved'
        )
    );
END;
$$;
