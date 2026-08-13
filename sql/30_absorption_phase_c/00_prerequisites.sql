DO $$
BEGIN
    IF to_regclass('analytics.v_ciclo_comercial_reconciliado') IS NULL THEN
        RAISE EXCEPTION 'Falta analytics.v_ciclo_comercial_reconciliado';
    END IF;

    IF to_regclass('analytics.fact_movimientos_stock') IS NULL THEN
        RAISE EXCEPTION 'Falta analytics.fact_movimientos_stock';
    END IF;

    IF to_regclass('analytics.int_ciclo_comercial_unidad') IS NULL THEN
        RAISE EXCEPTION 'Falta analytics.int_ciclo_comercial_unidad';
    END IF;
END $$;


DO $$
DECLARE
    n bigint;
BEGIN
    SELECT count(*) INTO n
    FROM (
        SELECT codigo_unidad
        FROM analytics.fact_movimientos_stock
        WHERE transition_applied
          AND codigo_proyecto IS NOT NULL
        GROUP BY codigo_unidad
        HAVING count(DISTINCT codigo_proyecto) > 1
    ) x;

    IF n > 0 THEN
        RAISE EXCEPTION
            'OPEN BUSINESS RULE: % unidades tienen movimientos efectivos en más de un codigo_proyecto. Resolver asignación temporal de proyecto antes de stock por proyecto.',
            n;
    END IF;
END $$;
