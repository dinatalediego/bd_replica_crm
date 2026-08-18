-- Quality override for sale-date rule v2.
--
-- The business rule resolves exactly one effective pago_ci value per proforma:
-- latest by fecha_actualizacion/id. Therefore the hard parse gate must evaluate
-- that same effective value, not stale historical rows that are no longer used.
-- Historical malformed values remain visible as WARN debt.

CREATE OR REPLACE PROCEDURE analytics.run_sale_date_pago_ci_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
    -------------------------------------------------------------------------
    -- HARD: only the effective/latest pago_ci value can contaminate decisions.
    -------------------------------------------------------------------------
    WITH latest_pago_ci AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text AS codigo_proforma,
            de.id,
            de.valor,
            de.fecha_actualizacion
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='pago_ci'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    )
    SELECT count(*) INTO n
    FROM latest_pago_ci
    WHERE valor IS NOT NULL
      AND btrim(valor)<>''
      AND analytics.try_parse_business_date(valor) IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'PAGO_CI_DATE_PARSE_ERROR',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'scope','LATEST_EFFECTIVE_VALUE_PER_PROFORMA',
            'business_field','datos_extras.pago_ci',
            'meaning','El valor efectivo de pago de cuota inicial debe poder convertirse a date'
        )
    );

    -------------------------------------------------------------------------
    -- WARN: preserve visibility of malformed superseded historical rows.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM raw_cygnus.datos_extras de
    WHERE lower(de.entidad)='proforma'
      AND lower(de.nombre)='pago_ci'
      AND de.valor IS NOT NULL
      AND btrim(de.valor)<>''
      AND analytics.try_parse_business_date(de.valor) IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'PAGO_CI_HISTORICAL_PARSE_DEBT',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'scope','ALL_RAW_HISTORY',
            'meaning','Deuda histórica de formato; no bloquea si el valor efectivo actual es parseable'
        )
    );

    -------------------------------------------------------------------------
    -- Semantic checks on the governed lifecycle.
    -------------------------------------------------------------------------
    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad c
    WHERE lower(coalesce(c.tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
      AND c.fecha_pago_ci IS NOT NULL
      AND (
            c.fecha_venta IS DISTINCT FROM c.fecha_pago_ci
         OR c.metodo_fecha_venta <> 'PAGO_CI_DATOS_EXTRAS'
      );

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'PAGO_CI_NOT_PRIORITIZED_AS_SALE_DATE',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'expected','fecha_venta = fecha_pago_ci for residential cycles whenever effective pago_ci exists'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad c
    WHERE c.fecha_separacion >= DATE '2026-01-01'
      AND c.metodo_fecha_venta = 'LEGACY_FECHA_FIRMA_PRE_2026';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'POST_2026_LEGACY_SALE_DATE_USED',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'rule','Desde 2026 la fecha del proceso Venta es cierre de proceso, no conversión'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad c
    WHERE c.fecha_separacion >= DATE '2026-01-01'
      AND lower(coalesce(c.tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
      AND c.resultado_ciclo='VENTA'
      AND c.metodo_fecha_venta <> 'PAGO_CI_DATOS_EXTRAS';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'POST_2026_SALE_WITHOUT_PAGO_CI',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'expected_sale_evidence','PAGO_CI_DATOS_EXTRAS'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad c
    WHERE lower(coalesce(c.tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
      AND c.fecha_pago_ci IS NOT NULL
      AND c.resultado_ciclo='ABIERTA';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'OPEN_RESIDENTIAL_CYCLE_WITH_PAGO_CI',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'meaning','Un ciclo con pago de cuota inicial efectivo no puede permanecer ABIERTA'
        )
    );
END;
$$;
