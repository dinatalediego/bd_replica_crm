CREATE OR REPLACE PROCEDURE analytics.run_absorption_phase_b_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
    -- Solo conservar última ejecución lógica mediante timestamps; no borrar historia.
    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad
    WHERE fecha_separacion < fecha_entrada_stock;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SEPARATION_ANALYTIC_BEFORE_STOCK_ENTRY',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object('expected',0)
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad
    WHERE fecha_venta IS NOT NULL
      AND fecha_venta < fecha_separacion;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SALE_BEFORE_SEPARATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object('expected',0)
    );


    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad
    WHERE fecha_venta IS NOT NULL
      AND primera_fecha_caida IS NOT NULL
      AND fecha_venta > primera_fecha_caida;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SALE_AFTER_FIRST_CANCELLATION',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'meaning','Revisar secuencia o necesidad futura de cycle_sequence'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad
    WHERE fecha_venta IS NOT NULL
      AND primera_fecha_caida IS NOT NULL
      AND fecha_venta = primera_fecha_caida;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SALE_AND_CANCELLATION_SAME_DAY',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'open_business_rule','No existe hora autoritativa para desempatar fuentes distintas'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.fact_movimientos_stock
    WHERE tipo_evento='CAIDA'
      AND transition_applied=false;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'CANCELLATION_WITHOUT_SEPARATED_STATE',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'meaning','Evento RAW conservado, pero no produjo reingreso efectivo'
        )
    );

    SELECT count(*) INTO n
    FROM (
        SELECT codigo_unidad, sum(delta_stock) stock
        FROM analytics.fact_movimientos_stock
        GROUP BY codigo_unidad
        HAVING sum(delta_stock) < 0
    ) x;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'NEGATIVE_CURRENT_STOCK_BY_UNIT',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object('expected',0)
    );

    SELECT count(*) INTO n
    FROM raw_cygnus.datos_extras
    WHERE lower(entidad)='proforma'
      AND lower(nombre)='fecha_de_minuta'
      AND valor IS NOT NULL
      AND btrim(valor)<>''
      AND analytics.try_parse_business_date(valor) IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'FECHA_DE_MINUTA_PARSE_ERROR',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'accepted_formats',jsonb_build_array('YYYY-MM-DD','DD-MM-YYYY')
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad
    WHERE fecha_separacion_ajustada;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SEPARATION_DATE_ADJUSTED_TO_STOCK_ENTRY',
        'INFO',
        n,
        'INFO',
        jsonb_build_object(
            'rule','RAW preserved; analytic date replaced by fecha_entrada_stock'
        )
    );
END;
$$;
