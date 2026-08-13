CREATE OR REPLACE PROCEDURE analytics.refresh_absorption_phase_b_full()
LANGUAGE plpgsql
AS $$
BEGIN
    -- INITIAL / CONTROLLED BACKFILL.
    -- Daily operation will use incremental procedure.

    TRUNCATE TABLE
        analytics.fact_movimientos_stock,
        analytics.int_ciclo_comercial_unidad,
        analytics.int_proforma_minuta,
        analytics.int_unidad_entrada_stock;

    -------------------------------------------------------------------------
    -- A. Entrada al stock: primera fecha observable de proforma_unidad/unidad
    -------------------------------------------------------------------------
    INSERT INTO analytics.int_unidad_entrada_stock(
        codigo_unidad,
        codigo_proyecto,
        fecha_entrada_stock,
        metodo_fecha_entrada_stock,
        source_proforma_unidad_id,
        primera_codigo_proforma,
        source_first_seen_at
    )
    WITH ranked AS (
        SELECT
            pu.codigo_unidad::text AS codigo_unidad,
            pu.codigo_proyecto::text AS codigo_proyecto,
            pu.fecha_creacion::date AS fecha_creacion,
            pu.id AS source_id,
            pu.codigo_proforma::text AS codigo_proforma,
            row_number() OVER (
                PARTITION BY pu.codigo_unidad
                ORDER BY pu.fecha_creacion NULLS LAST, pu.id
            ) AS rn
        FROM raw_cygnus.proforma_unidad pu
        WHERE pu.codigo_unidad IS NOT NULL
          AND pu.fecha_creacion IS NOT NULL
    )
    SELECT
        codigo_unidad,
        codigo_proyecto,
        fecha_creacion,
        'FIRST_PROFORMA_UNIDAD_FECHA_CREACION',
        source_id,
        codigo_proforma,
        fecha_creacion
    FROM ranked
    WHERE rn = 1;

    -------------------------------------------------------------------------
    -- B. Datos extra de proforma, pivotados una sola vez
    -------------------------------------------------------------------------
    WITH extra_ranked AS (
        SELECT
            de.id,
            de.codigo::text AS codigo_proforma,
            lower(de.nombre) AS nombre,
            de.valor,
            de.fecha_actualizacion,
            row_number() OVER (
                PARTITION BY de.codigo, lower(de.nombre)
                ORDER BY de.fecha_actualizacion DESC NULLS LAST, de.id DESC
            ) rn
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad) = 'proforma'
          AND lower(de.nombre) IN (
              'pago_ci',
              'fecha_de_minuta',
              'monto_total_pagado',
              'monto_pagado_de_cuota_inicial',
              'asesor_compartido'
          )
    ),
    extras AS (
        SELECT
            codigo_proforma,
            max(id) FILTER (WHERE nombre='fecha_de_minuta') AS fecha_minuta_source_id,
            max(valor) FILTER (WHERE nombre='fecha_de_minuta') AS fecha_de_minuta_raw,
            max(valor) FILTER (WHERE nombre='pago_ci') AS pago_ci_raw,
            max(valor) FILTER (WHERE nombre='monto_total_pagado') AS monto_total_pagado_raw,
            max(valor) FILTER (WHERE nombre='monto_pagado_de_cuota_inicial') AS monto_pagado_ci_raw,
            max(valor) FILTER (WHERE nombre='asesor_compartido') AS asesor_compartido
        FROM extra_ranked
        WHERE rn = 1
        GROUP BY codigo_proforma
    ),
    sep_ranked AS (
        SELECT
            p.*,
            row_number() OVER (
                PARTITION BY p.codigo_proforma, p.codigo_unidad
                ORDER BY p.fecha_inicio, p.id
            ) rn
        FROM raw_cygnus.procesos p
        WHERE p.nombre = 'Separacion'
          AND p.estado = 'Activo'
          AND p.fecha_inicio IS NOT NULL
          AND coalesce(p.nombre_flujo,'') <> 'Desistimiento de visita'
          AND lower(p.tipo_unidad_principal) IN (
              'departamento flat',
              'departamento duplex'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM etl_control.business_exclusions e
              WHERE e.entity_type='PROFORMA'
                AND e.entity_key=p.codigo_proforma::text
                AND e.scope='COMMERCIAL_ANALYTICS'
                AND e.is_active
                AND (e.valid_from IS NULL OR e.valid_from <= p.fecha_inicio::date)
                AND (e.valid_to IS NULL OR e.valid_to >= p.fecha_inicio::date)
          )
    )
    INSERT INTO analytics.int_proforma_minuta(
        codigo_proforma, codigo_unidad, codigo_proyecto,
        documento_cliente, usuario_separacion, tipo_unidad_principal,
        estado_separacion, separacion_source_id,
        fecha_separacion_raw, fecha_entrada_stock, fecha_separacion_analitica,
        fecha_separacion_ajustada, motivo_ajuste_fecha,
        datos_extras_fecha_minuta_id, fecha_de_minuta_raw, fecha_de_minuta,
        pago_ci_raw, pago_ci,
        monto_total_pagado_raw, monto_total_pagado,
        monto_pagado_de_cuota_inicial_raw, monto_pagado_de_cuota_inicial,
        monto_pagado_cuota_inicial, asesor_compartido
    )
    SELECT
        s.codigo_proforma::text,
        s.codigo_unidad::text,
        s.codigo_proyecto::text,
        s.documento_cliente::text,
        s.usuario_separacion::text,
        s.tipo_unidad_principal::text,
        s.estado::text,
        s.id,
        s.fecha_inicio::date,
        st.fecha_entrada_stock,
        CASE
            WHEN st.fecha_entrada_stock IS NOT NULL
             AND s.fecha_inicio::date < st.fecha_entrada_stock
            THEN st.fecha_entrada_stock
            ELSE s.fecha_inicio::date
        END,
        (
            st.fecha_entrada_stock IS NOT NULL
            AND s.fecha_inicio::date < st.fecha_entrada_stock
        ),
        CASE
            WHEN st.fecha_entrada_stock IS NOT NULL
             AND s.fecha_inicio::date < st.fecha_entrada_stock
            THEN 'SEPARACION_ANTERIOR_A_ENTRADA_STOCK'
        END,
        x.fecha_minuta_source_id,
        x.fecha_de_minuta_raw,
        analytics.try_parse_business_date(x.fecha_de_minuta_raw),
        x.pago_ci_raw,
        analytics.try_parse_numeric(x.pago_ci_raw),
        x.monto_total_pagado_raw,
        analytics.try_parse_numeric(x.monto_total_pagado_raw),
        x.monto_pagado_ci_raw,
        analytics.try_parse_numeric(x.monto_pagado_ci_raw),
        coalesce(
            analytics.try_parse_numeric(x.monto_total_pagado_raw),
            analytics.try_parse_numeric(x.monto_pagado_ci_raw)
        ),
        x.asesor_compartido
    FROM sep_ranked s
    LEFT JOIN analytics.int_unidad_entrada_stock st
      ON st.codigo_unidad = s.codigo_unidad::text
    LEFT JOIN extras x
      ON x.codigo_proforma = s.codigo_proforma::text
    WHERE s.rn = 1;

    -------------------------------------------------------------------------
    -- C. Ciclo comercial unitario
    --
    -- No se usa MAX() ciego para resolver Venta/Caída.
    -- Se toma:
    --   * primera Separacion del ciclo (Fase A validó ausencia de ciclos múltiples)
    --   * primera Venta >= fecha_separacion_analitica
    --   * Anulaciones >= fecha_separacion_analitica
    --   * fecha_de_minuta SOLO para unidad residencial bajo regla vigente
    -------------------------------------------------------------------------
    WITH sep_all AS (
        SELECT
            p.*,
            row_number() OVER (
                PARTITION BY p.codigo_proforma,p.codigo_unidad
                ORDER BY p.fecha_inicio,p.id
            ) rn
        FROM raw_cygnus.procesos p
        WHERE p.nombre='Separacion'
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
    ),
    minute_extra AS (
        SELECT DISTINCT ON (de.codigo)
            de.codigo::text codigo_proforma,
            de.id source_id,
            analytics.try_parse_business_date(de.valor) fecha_de_minuta
        FROM raw_cygnus.datos_extras de
        WHERE lower(de.entidad)='proforma'
          AND lower(de.nombre)='fecha_de_minuta'
        ORDER BY de.codigo, de.fecha_actualizacion DESC NULLS LAST, de.id DESC
    ),
    sep_base AS (
        SELECT
            s.*,
            st.fecha_entrada_stock,
            CASE
                WHEN st.fecha_entrada_stock IS NOT NULL
                 AND s.fecha_inicio::date < st.fecha_entrada_stock
                THEN st.fecha_entrada_stock
                ELSE s.fecha_inicio::date
            END AS fecha_sep_analitica,
            (
                st.fecha_entrada_stock IS NOT NULL
                AND s.fecha_inicio::date < st.fecha_entrada_stock
            ) AS fecha_sep_ajustada
        FROM sep_all s
        LEFT JOIN analytics.int_unidad_entrada_stock st
          ON st.codigo_unidad=s.codigo_unidad::text
        WHERE s.rn=1
    )
    INSERT INTO analytics.int_ciclo_comercial_unidad(
        codigo_proforma, codigo_unidad, codigo_proyecto,
        separacion_source_id, fecha_entrada_stock,
        fecha_separacion_raw, fecha_separacion, fecha_separacion_ajustada,
        venta_source_id, fecha_firma_legacy,
        datos_extras_fecha_minuta_id, fecha_de_minuta,
        fecha_venta, metodo_fecha_venta,
        primera_fecha_caida, ultima_fecha_caida, cantidad_anulaciones,
        resultado_ciclo, dias_separacion_venta, dias_separacion_caida,
        documento_cliente, asesor, tipo_unidad_principal
    )
    SELECT
        b.codigo_proforma::text,
        b.codigo_unidad::text,
        b.codigo_proyecto::text,
        b.id,
        b.fecha_entrada_stock,
        b.fecha_inicio::date,
        b.fecha_sep_analitica,
        b.fecha_sep_ajustada,
        v.id,
        v.fecha_firma_legacy,
        me.source_id,
        me.fecha_de_minuta,
        calc.fecha_venta,
        calc.metodo_fecha_venta,
        c.primera_fecha_caida,
        c.ultima_fecha_caida,
        coalesce(c.cantidad_anulaciones,0),
        CASE
            WHEN calc.fecha_venta IS NOT NULL
             AND (
                c.primera_fecha_caida IS NULL
                OR calc.fecha_venta <= c.primera_fecha_caida
             )
                THEN 'VENTA'
            WHEN c.primera_fecha_caida IS NOT NULL
                THEN 'CAIDA'
            ELSE 'ABIERTA'
        END,
        CASE
            WHEN calc.fecha_venta IS NOT NULL
            THEN calc.fecha_venta - b.fecha_sep_analitica
        END,
        CASE
            WHEN c.primera_fecha_caida IS NOT NULL
            THEN c.primera_fecha_caida - b.fecha_sep_analitica
        END,
        b.documento_cliente::text,
        b.usuario_separacion::text,
        b.tipo_unidad_principal::text
    FROM sep_base b

    -- Primera Venta observable a partir de la separación analítica.
    LEFT JOIN LATERAL (
        SELECT
            p.id,
            p.fecha_inicio::date AS fecha_firma_legacy
        FROM raw_cygnus.procesos p
        WHERE p.nombre='Venta'
          AND p.codigo_proforma=b.codigo_proforma
          AND p.codigo_unidad=b.codigo_unidad
          AND p.fecha_inicio IS NOT NULL
          AND p.fecha_inicio::date >= b.fecha_sep_analitica
        ORDER BY p.fecha_inicio,p.id
        LIMIT 1
    ) v ON true

    -- Solo anulaciones posteriores o iguales a la separación analítica.
    LEFT JOIN LATERAL (
        SELECT
            min(p.fecha_inicio::date) AS primera_fecha_caida,
            max(p.fecha_inicio::date) AS ultima_fecha_caida,
            count(*)::int AS cantidad_anulaciones
        FROM raw_cygnus.procesos p
        WHERE p.nombre='Anulacion'
          AND p.codigo_proforma=b.codigo_proforma
          AND p.codigo_unidad=b.codigo_unidad
          AND p.fecha_inicio IS NOT NULL
          AND p.fecha_inicio::date >= b.fecha_sep_analitica
          AND coalesce(p.nombre_flujo,'') <> 'Desistimiento de visita'
    ) c ON true

    -- OPEN BUSINESS RULE: no propagar minuta a accesorios.
    LEFT JOIN minute_extra me
      ON me.codigo_proforma=b.codigo_proforma::text
     AND lower(b.tipo_unidad_principal) IN (
         'departamento flat',
         'departamento duplex'
     )

    LEFT JOIN LATERAL (
        SELECT
            coalesce(
                me.fecha_de_minuta,
                CASE
                    WHEN b.fecha_sep_analitica < DATE '2026-01-01'
                    THEN v.fecha_firma_legacy
                END
            ) AS fecha_venta,
            CASE
                WHEN me.fecha_de_minuta IS NOT NULL
                    THEN 'FECHA_DE_MINUTA'
                WHEN b.fecha_sep_analitica < DATE '2026-01-01'
                 AND v.fecha_firma_legacy IS NOT NULL
                    THEN 'LEGACY_FECHA_FIRMA_PRE_2026'
                ELSE 'NO_CONFIRMADA'
            END AS metodo_fecha_venta
    ) calc ON true;

    -------------------------------------------------------------------------
    -- D. Ledger / state machine
    --
    -- Event sourcing:
    -- ALTA_STOCK synthetic
    -- SEPARACION from process
    -- VENTA from authoritative cycle date
    -- ANULACION from process
    -------------------------------------------------------------------------
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
                WHEN c.metodo_fecha_venta='FECHA_DE_MINUTA'
                    THEN 'datos_extras'
                ELSE 'procesos'
            END,
            CASE
                WHEN c.metodo_fecha_venta='FECHA_DE_MINUTA'
                    THEN c.datos_extras_fecha_minuta_id
                ELSE c.venta_source_id
            END,
            CASE
                WHEN c.metodo_fecha_venta='FECHA_DE_MINUTA'
                    THEN 'fecha_de_minuta:' || c.datos_extras_fecha_minuta_id::text
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
    ),
    ordered AS (
        SELECT
            e.*,
            row_number() OVER (
                PARTITION BY e.codigo_unidad
                ORDER BY e.fecha_evento, e.priority, e.source_event_key
            ) AS seq
        FROM events e
        WHERE e.fecha_evento IS NOT NULL
    ),
    sm AS (
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
            s.rn + 1,
            s.estado_nuevo AS estado_anterior,
            CASE
                WHEN o.tipo_evento='ALTA_STOCK'
                 AND s.estado_nuevo='NOT_OFFERED'
                    THEN 'AVAILABLE'
                WHEN o.tipo_evento='SEPARACION'
                 AND s.estado_nuevo='AVAILABLE'
                    THEN 'SEPARATED'
                WHEN o.tipo_evento='VENTA'
                 AND s.estado_nuevo='SEPARATED'
                    THEN 'SOLD'
                WHEN o.tipo_evento='CAIDA'
                 AND s.estado_nuevo='SEPARATED'
                    THEN 'AVAILABLE'
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
        movement_id, source_table, source_id, source_event_key,
        codigo_proforma, codigo_unidad, codigo_proyecto,
        fecha_evento, tipo_evento, event_order,
        estado_anterior, estado_nuevo,
        transition_applied, transition_reason,
        delta_stock, delta_separadas_activas, delta_ventas, delta_caidas
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

    CALL analytics.run_absorption_phase_b_qa();
END;
$$;
