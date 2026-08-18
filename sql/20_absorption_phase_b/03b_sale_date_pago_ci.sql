-- Commercial sale-date rule v2.
--
-- Business meaning:
--   * From 2026 onward, commercial conversion is confirmed by the proforma
--     datos_extra `pago_ci` (payment of the initial instalment).
--   * Before 2026, `pago_ci` still has priority when present; only when it is
--     missing do we fall back to the legacy Venta process date.
--   * `fecha_firma_legacy` / Venta process date remains useful as the date when
--     the sales process was closed, but from 2026 it is NOT conversion evidence.
--   * `fecha_de_minuta` remains a separate administrative/legal milestone and
--     no longer drives `fecha_venta`.
--
-- The file wraps the existing Phase-B full refresh instead of duplicating its
-- extraction logic. The base refresh runs first; this governed post-step then
-- recalculates sale identity/outcome and rebuilds the stock ledger from the
-- corrected lifecycle. This keeps direct CALLs and the incremental wrapper safe.

CREATE OR REPLACE PROCEDURE analytics.run_sale_date_pago_ci_qa()
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
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
        'PAGO_CI_DATE_PARSE_ERROR',
        'ERROR',
        n,
        CASE WHEN n=0 THEN 'PASS' ELSE 'FAIL' END,
        jsonb_build_object(
            'business_field','datos_extras.pago_ci',
            'meaning','La fecha de pago de cuota inicial debe poder convertirse a date'
        )
    );

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
            'expected','fecha_venta = fecha_pago_ci for residential cycles whenever pago_ci exists'
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
            'meaning','Un ciclo con pago de cuota inicial no puede permanecer ABIERTA'
        )
    );
END;
$$;


CREATE OR REPLACE PROCEDURE analytics.apply_sale_date_pago_ci_rule()
LANGUAGE plpgsql
AS $$
BEGIN
    -------------------------------------------------------------------------
    -- 1. Persist payment-date provenance on the proforma intermediate table.
    -------------------------------------------------------------------------
    WITH payment_extra AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text AS codigo_proforma,
            de.id AS source_id,
            de.valor AS pago_ci_raw,
            analytics.try_parse_business_date(de.valor) AS fecha_pago_ci
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='pago_ci'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    ), resolved AS (
        SELECT
            p.codigo_proforma,
            p.codigo_unidad,
            pe.source_id,
            pe.pago_ci_raw,
            pe.fecha_pago_ci
        FROM analytics.int_proforma_minuta p
        LEFT JOIN payment_extra pe
          ON pe.codigo_proforma=p.codigo_proforma
    )
    UPDATE analytics.int_proforma_minuta p
       SET datos_extras_pago_ci_id=r.source_id,
           pago_ci_raw=coalesce(r.pago_ci_raw,p.pago_ci_raw),
           fecha_pago_ci=r.fecha_pago_ci,
           refreshed_at=now()
      FROM resolved r
     WHERE p.codigo_proforma=r.codigo_proforma
       AND p.codigo_unidad=r.codigo_unidad;

    -------------------------------------------------------------------------
    -- 2. Recalculate the authoritative sale date and lifecycle outcome.
    --
    -- Equivalent business rule:
    --   Fecha_Venta = COALESCE(
    --       Fecha_PagoCI,
    --       IF(fecha_separacion < 2026-01-01, Fecha_Proceso_Venta, NULL)
    --   )
    -- Payment CI is applied only to the residential main-unit cycle, matching
    -- the commercial Power Query contract (flat / duplex).
    -------------------------------------------------------------------------
    WITH payment_extra AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text AS codigo_proforma,
            de.id AS source_id,
            analytics.try_parse_business_date(de.valor) AS fecha_pago_ci
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='pago_ci'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    ), sale_base AS (
        SELECT
            c.codigo_proforma,
            c.codigo_unidad,
            pe.source_id AS datos_extras_pago_ci_id,
            pe.fecha_pago_ci,
            CASE
                WHEN lower(coalesce(c.tipo_unidad_principal,'')) IN (
                         'departamento flat','departamento duplex'
                     )
                 AND pe.fecha_pago_ci IS NOT NULL
                    THEN pe.fecha_pago_ci
                WHEN c.fecha_separacion < DATE '2026-01-01'
                 AND c.fecha_firma_legacy IS NOT NULL
                    THEN c.fecha_firma_legacy
                ELSE NULL::date
            END AS nueva_fecha_venta,
            CASE
                WHEN lower(coalesce(c.tipo_unidad_principal,'')) IN (
                         'departamento flat','departamento duplex'
                     )
                 AND pe.fecha_pago_ci IS NOT NULL
                    THEN 'PAGO_CI_DATOS_EXTRAS'
                WHEN c.fecha_separacion < DATE '2026-01-01'
                 AND c.fecha_firma_legacy IS NOT NULL
                    THEN 'LEGACY_FECHA_FIRMA_PRE_2026'
                ELSE 'NO_CONFIRMADA'
            END AS nuevo_metodo_fecha_venta,
            c.primera_fecha_caida,
            c.fecha_separacion
        FROM analytics.int_ciclo_comercial_unidad c
        LEFT JOIN payment_extra pe
          ON pe.codigo_proforma=c.codigo_proforma
    ), resolved AS (
        SELECT
            s.*,
            CASE
                WHEN s.nueva_fecha_venta IS NOT NULL
                 AND (
                        s.primera_fecha_caida IS NULL
                     OR s.nueva_fecha_venta <= s.primera_fecha_caida
                 )
                    THEN 'VENTA'
                WHEN s.primera_fecha_caida IS NOT NULL
                    THEN 'CAIDA'
                ELSE 'ABIERTA'
            END AS nuevo_resultado_ciclo
        FROM sale_base s
    )
    UPDATE analytics.int_ciclo_comercial_unidad c
       SET datos_extras_pago_ci_id=r.datos_extras_pago_ci_id,
           fecha_pago_ci=r.fecha_pago_ci,
           fecha_venta=r.nueva_fecha_venta,
           metodo_fecha_venta=r.nuevo_metodo_fecha_venta,
           resultado_ciclo=r.nuevo_resultado_ciclo,
           dias_separacion_venta=CASE
               WHEN r.nueva_fecha_venta IS NOT NULL
               THEN r.nueva_fecha_venta-r.fecha_separacion
           END,
           refreshed_at=now()
      FROM resolved r
     WHERE c.codigo_proforma=r.codigo_proforma
       AND c.codigo_unidad=r.codigo_unidad;

    -------------------------------------------------------------------------
    -- 3. Rebuild the ledger from the corrected authoritative lifecycle.
    -------------------------------------------------------------------------
    TRUNCATE TABLE analytics.fact_movimientos_stock;

    WITH RECURSIVE events AS (
        SELECT
            st.codigo_unidad,
            st.codigo_proyecto,
            st.primera_codigo_proforma AS codigo_proforma,
            st.fecha_entrada_stock AS fecha_evento,
            'ALTA_STOCK'::text AS tipo_evento,
            10 AS priority,
            'proforma_unidad'::text AS source_table,
            st.source_proforma_unidad_id AS source_id,
            'proforma_unidad:' || st.source_proforma_unidad_id::text AS source_event_key
        FROM analytics.int_unidad_entrada_stock st

        UNION ALL

        SELECT
            c.codigo_unidad,
            c.codigo_proyecto,
            c.codigo_proforma,
            c.fecha_separacion,
            'SEPARACION',
            20,
            'procesos',
            c.separacion_source_id,
            'separacion:' || c.separacion_source_id::text
        FROM analytics.int_ciclo_comercial_unidad c
        WHERE c.fecha_separacion IS NOT NULL

        UNION ALL

        SELECT
            c.codigo_unidad,
            c.codigo_proyecto,
            c.codigo_proforma,
            c.fecha_venta,
            'VENTA',
            30,
            CASE
                WHEN c.metodo_fecha_venta='PAGO_CI_DATOS_EXTRAS'
                    THEN 'datos_extras'
                ELSE 'procesos'
            END,
            CASE
                WHEN c.metodo_fecha_venta='PAGO_CI_DATOS_EXTRAS'
                    THEN c.datos_extras_pago_ci_id
                ELSE c.venta_source_id
            END,
            CASE
                WHEN c.metodo_fecha_venta='PAGO_CI_DATOS_EXTRAS'
                    THEN 'pago_ci:' || c.datos_extras_pago_ci_id::text
                ELSE 'venta:' || c.venta_source_id::text
            END
        FROM analytics.int_ciclo_comercial_unidad c
        WHERE c.fecha_venta IS NOT NULL

        UNION ALL

        SELECT
            p.codigo_unidad::text,
            p.codigo_proyecto::text,
            p.codigo_proforma::text,
            p.fecha_inicio::date,
            'CAIDA',
            40,
            'procesos',
            p.id,
            'anulacion:' || p.id::text
        FROM raw_cygnus.procesos p
        WHERE p.nombre='Anulacion'
          AND p.fecha_inicio IS NOT NULL
          AND coalesce(p.nombre_flujo,'') <> 'Desistimiento de visita'
          AND NOT EXISTS (
              SELECT 1
              FROM etl_control.business_exclusions e
              WHERE e.entity_type='PROFORMA'
                AND e.entity_key=p.codigo_proforma::text
                AND e.scope='COMMERCIAL_ANALYTICS'
                AND e.is_active
          )
    ), ordered AS (
        SELECT
            e.*,
            row_number() OVER (
                PARTITION BY e.codigo_unidad
                ORDER BY e.fecha_evento, e.priority, e.source_event_key
            ) AS seq
        FROM events e
        WHERE e.fecha_evento IS NOT NULL
    ), sm AS (
        SELECT
            o.*,
            1 AS rn,
            'NOT_OFFERED'::text AS estado_anterior,
            CASE
                WHEN o.tipo_evento='ALTA_STOCK' THEN 'AVAILABLE'
                ELSE 'NOT_OFFERED'
            END::text AS estado_nuevo,
            (o.tipo_evento='ALTA_STOCK') AS transition_applied
        FROM ordered o
        WHERE o.seq=1

        UNION ALL

        SELECT
            o.*,
            s.rn+1,
            s.estado_nuevo AS estado_anterior,
            CASE
                WHEN o.tipo_evento='ALTA_STOCK'
                 AND s.estado_nuevo='NOT_OFFERED' THEN 'AVAILABLE'
                WHEN o.tipo_evento='SEPARACION'
                 AND s.estado_nuevo='AVAILABLE' THEN 'SEPARATED'
                WHEN o.tipo_evento='VENTA'
                 AND s.estado_nuevo='SEPARATED' THEN 'SOLD'
                WHEN o.tipo_evento='CAIDA'
                 AND s.estado_nuevo='SEPARATED' THEN 'AVAILABLE'
                ELSE s.estado_nuevo
            END AS estado_nuevo,
            CASE
                WHEN o.tipo_evento='ALTA_STOCK'
                 AND s.estado_nuevo='NOT_OFFERED' THEN true
                WHEN o.tipo_evento='SEPARACION'
                 AND s.estado_nuevo='AVAILABLE' THEN true
                WHEN o.tipo_evento='VENTA'
                 AND s.estado_nuevo='SEPARATED' THEN true
                WHEN o.tipo_evento='CAIDA'
                 AND s.estado_nuevo='SEPARATED' THEN true
                ELSE false
            END AS transition_applied
        FROM sm s
        JOIN ordered o
          ON o.codigo_unidad=s.codigo_unidad
         AND o.seq=s.seq+1
    )
    INSERT INTO analytics.fact_movimientos_stock(
        movement_id,source_table,source_id,source_event_key,
        codigo_proforma,codigo_unidad,codigo_proyecto,
        fecha_evento,tipo_evento,event_order,
        estado_anterior,estado_nuevo,
        transition_applied,transition_reason,
        delta_stock,delta_separadas_activas,delta_ventas,delta_caidas
    )
    SELECT
        md5(
            coalesce(codigo_unidad,'') || '|' ||
            fecha_evento::text || '|' ||
            tipo_evento || '|' ||
            source_event_key
        ),
        source_table,
        source_id,
        source_event_key,
        codigo_proforma,
        codigo_unidad,
        codigo_proyecto,
        fecha_evento,
        tipo_evento,
        seq,
        estado_anterior,
        estado_nuevo,
        transition_applied,
        CASE
            WHEN transition_applied THEN 'VALID_STATE_TRANSITION'
            ELSE 'EVENT_WITHOUT_VALID_STATE_TRANSITION'
        END,
        CASE
            WHEN transition_applied AND tipo_evento='ALTA_STOCK' THEN 1
            WHEN transition_applied AND tipo_evento='SEPARACION' THEN -1
            WHEN transition_applied AND tipo_evento='CAIDA' THEN 1
            ELSE 0
        END,
        CASE
            WHEN transition_applied AND tipo_evento='SEPARACION' THEN 1
            WHEN transition_applied AND tipo_evento IN ('VENTA','CAIDA') THEN -1
            ELSE 0
        END,
        CASE
            WHEN transition_applied AND tipo_evento='VENTA' THEN 1
            ELSE 0
        END,
        CASE
            WHEN transition_applied AND tipo_evento='CAIDA' THEN 1
            ELSE 0
        END
    FROM sm;

    -- Base QA is rerun so the latest generic checks reflect the corrected dates.
    CALL analytics.run_absorption_phase_b_qa();
    CALL analytics.run_sale_date_pago_ci_qa();
END;
$$;


-- Wrap the existing Phase-B full procedure. On each install, 03_refresh_full.sql
-- has just recreated the base implementation at this name, so this sequence is
-- idempotent even when the environment was already upgraded previously.
DROP PROCEDURE IF EXISTS analytics.refresh_absorption_phase_b_full_base();
ALTER PROCEDURE analytics.refresh_absorption_phase_b_full()
    RENAME TO refresh_absorption_phase_b_full_base;

CREATE OR REPLACE PROCEDURE analytics.refresh_absorption_phase_b_full()
LANGUAGE plpgsql
AS $$
BEGIN
    CALL analytics.refresh_absorption_phase_b_full_base();
    CALL analytics.apply_sale_date_pago_ci_rule();
END;
$$;
