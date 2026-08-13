CREATE OR REPLACE PROCEDURE analytics.run_absorption_reconciliation_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
    total_units bigint;
    state_units bigint;
BEGIN
    -------------------------------------------------------------------------
    -- A. Fecha venta validada nunca puede ser anterior a separación.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.v_ciclo_comercial_reconciliado
    WHERE fecha_venta_validada IS NOT NULL
      AND fecha_venta_validada < fecha_separacion;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'VALIDATED_SALE_BEFORE_SEPARATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object('expected',0)
    );

    -------------------------------------------------------------------------
    -- B. Fechas documentales inválidas: visibles, no silenciadas.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.v_ciclo_comercial_reconciliado
    WHERE fecha_venta_anterior_separacion;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'DOCUMENTAL_SALE_DATE_BEFORE_SEPARATION',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'treatment',
            'fecha_venta_documental preserved; fecha_venta_validada=NULL'
        )
    );

    -------------------------------------------------------------------------
    -- C. Venta y caída el mismo día.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.v_ciclo_comercial_reconciliado
    WHERE venta_caida_mismo_dia;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'SALE_AND_CANCELLATION_SAME_DAY_OPEN_RULE',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'open_business_rule',
            'No authoritative common intraday timestamp available'
        )
    );

    -------------------------------------------------------------------------
    -- D. Divergencia workflow vs inventario.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.v_ciclo_comercial_reconciliado
    WHERE reconciliation_status='DOCUMENTAL_VS_INVENTARIO';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'DOCUMENTAL_INVENTORY_DIVERGENCE',
        'INFO',
        n,
        'INFO',
        jsonb_build_object(
            'meaning',
            'Workflow exists but did not necessarily produce a physical inventory transition'
        )
    );

    -------------------------------------------------------------------------
    -- E. Conservación del universo físico por estado actual.
    -------------------------------------------------------------------------
    SELECT count(*) INTO total_units
    FROM analytics.int_unidad_entrada_stock;

    SELECT count(*) INTO state_units
    FROM analytics.v_inventory_state_current
    WHERE current_inventory_state IN ('AVAILABLE','SEPARATED','SOLD');

    n := abs(total_units - state_units);

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'INVENTORY_STATE_CONSERVATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'units_entered_stock',total_units,
            'units_in_terminal_current_states',state_units
        )
    );

    -------------------------------------------------------------------------
    -- F. Reingresos efectivos nunca mayores que separaciones efectivas.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM (
        SELECT codigo_unidad
        FROM analytics.fact_movimientos_stock
        GROUP BY codigo_unidad
        HAVING count(*) FILTER (
            WHERE tipo_evento='CAIDA' AND transition_applied
        ) >
        count(*) FILTER (
            WHERE tipo_evento='SEPARACION' AND transition_applied
        )
    ) x;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    )
    VALUES (
        'EFFECTIVE_REENTRY_EXCEEDS_EFFECTIVE_SEPARATION',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object('expected',0)
    );

END;
$$;
