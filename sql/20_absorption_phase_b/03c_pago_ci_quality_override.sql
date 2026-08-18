-- Quality contract for commercial conversion evidence.
--
-- Proven source semantics:
--   pago_ci         = marker/status text, known positive value
--                     'Pagó cuota inicial (Minuta)'. It is NOT a date.
--   fecha_de_minuta = effective dated evidence used as Fecha_PagoCI_pm.
--
-- Safety principle for the Decision Engine:
--   * a valid fecha_de_minuta means converted and cannot remain ABIERTA;
--   * a confirmed pago_ci marker without a date is conversion evidence with
--     missing temporal precision. It is WARN data debt and must be excluded
--     from risk scoring rather than interpreted as "not paid";
--   * an unknown non-empty pago_ci value is unsafe source semantics.

CREATE OR REPLACE PROCEDURE analytics.run_sale_date_pago_ci_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
    -------------------------------------------------------------------------
    -- HARD: latest fecha_de_minuta must parse whenever it is populated.
    -------------------------------------------------------------------------
    WITH latest_fecha AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text AS codigo_proforma,
            de.valor
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='fecha_de_minuta'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    )
    SELECT count(*) INTO n
    FROM latest_fecha
    WHERE valor IS NOT NULL
      AND btrim(valor)<>''
      AND analytics.try_parse_business_date(valor) IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'FECHA_PAGO_CI_PARSE_ERROR',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'source_field','datos_extras.fecha_de_minuta',
            'business_alias','Fecha_PagoCI_pm',
            'meaning','La fecha efectiva de pago/conversión debe poder convertirse a date'
        )
    );

    -------------------------------------------------------------------------
    -- HARD: pago_ci is a categorical marker. Unknown populated values are not
    -- silently treated as positive or negative evidence.
    -------------------------------------------------------------------------
    WITH latest_marker AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text AS codigo_proforma,
            de.valor
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='pago_ci'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    )
    SELECT count(*) INTO n
    FROM latest_marker
    WHERE valor IS NOT NULL
      AND btrim(valor)<>''
      AND lower(btrim(valor)) <> lower('Pagó cuota inicial (Minuta)');

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'PAGO_CI_UNKNOWN_MARKER_VALUE',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'known_positive_marker','Pagó cuota inicial (Minuta)',
            'meaning','Un valor categórico desconocido no puede interpretarse automáticamente'
        )
    );

    -------------------------------------------------------------------------
    -- WARN: positive marker without dated conversion evidence. This is not a
    -- reason to call the opportunity risky; it is a reason to exclude it from
    -- scoring until temporal provenance is completed.
    -------------------------------------------------------------------------
    WITH latest AS (
        SELECT
            de.codigo::text AS codigo_proforma,
            lower(de.nombre) AS nombre,
            de.valor,
            row_number() OVER (
                PARTITION BY de.codigo, lower(de.nombre)
                ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
            ) AS rn
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre) IN ('pago_ci','fecha_de_minuta')
    ), pivot AS (
        SELECT
            codigo_proforma,
            max(valor) FILTER (WHERE nombre='pago_ci' AND rn=1) AS pago_ci_marker,
            max(analytics.try_parse_business_date(valor))
                FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS fecha_pago_ci
        FROM latest
        GROUP BY codigo_proforma
    )
    SELECT count(*) INTO n
    FROM pivot
    WHERE lower(btrim(coalesce(pago_ci_marker,''))) = lower('Pagó cuota inicial (Minuta)')
      AND fecha_pago_ci IS NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'PAGO_CI_MARKER_WITHOUT_FECHA_PAGO_CI',
        'WARNING',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'WARN' END,
        jsonb_build_object(
            'meaning','Conversión indicada por marcador, pero falta fecha; excluir del risk scoring'
        )
    );

    -------------------------------------------------------------------------
    -- INFO: a dated conversion may exist without the optional marker. The
    -- user's established Power Query treats fecha_de_minuta as dated evidence,
    -- so this is allowed and measured rather than rejected.
    -------------------------------------------------------------------------
    WITH latest AS (
        SELECT
            de.codigo::text AS codigo_proforma,
            lower(de.nombre) AS nombre,
            de.valor,
            row_number() OVER (
                PARTITION BY de.codigo, lower(de.nombre)
                ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
            ) AS rn
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre) IN ('pago_ci','fecha_de_minuta')
    ), pivot AS (
        SELECT
            codigo_proforma,
            max(valor) FILTER (WHERE nombre='pago_ci' AND rn=1) AS pago_ci_marker,
            max(analytics.try_parse_business_date(valor))
                FILTER (WHERE nombre='fecha_de_minuta' AND rn=1) AS fecha_pago_ci
        FROM latest
        GROUP BY codigo_proforma
    )
    SELECT count(*) INTO n
    FROM pivot
    WHERE (pago_ci_marker IS NULL OR btrim(pago_ci_marker)='')
      AND fecha_pago_ci IS NOT NULL;

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'FECHA_PAGO_CI_WITHOUT_MARKER',
        'INFO',
        n,
        'INFO',
        jsonb_build_object(
            'meaning','Fecha de conversión válida sin marcador pago_ci; permitido por contrato'
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
      AND c.fecha_de_minuta IS NOT NULL
      AND (
            c.fecha_venta IS DISTINCT FROM c.fecha_de_minuta
         OR c.metodo_fecha_venta <> 'FECHA_DE_MINUTA'
      );

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'FECHA_PAGO_CI_NOT_PRIORITIZED_AS_SALE_DATE',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'expected','fecha_venta = fecha_de_minuta when dated conversion evidence exists'
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
      AND c.metodo_fecha_venta <> 'FECHA_DE_MINUTA';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'POST_2026_SALE_WITHOUT_FECHA_PAGO_CI',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'expected_sale_evidence','FECHA_DE_MINUTA / Fecha_PagoCI_pm'
        )
    );

    SELECT count(*) INTO n
    FROM analytics.int_ciclo_comercial_unidad c
    WHERE lower(coalesce(c.tipo_unidad_principal,'')) IN (
              'departamento flat','departamento duplex'
          )
      AND c.fecha_de_minuta IS NOT NULL
      AND c.resultado_ciclo='ABIERTA';

    INSERT INTO observability.absorption_quality_results(
        check_name,severity,failed_rows,status,details
    ) VALUES (
        'OPEN_RESIDENTIAL_CYCLE_WITH_FECHA_PAGO_CI',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'meaning','Un ciclo con fecha efectiva de pago/conversión no puede permanecer ABIERTA'
        )
    );
END;
$$;
