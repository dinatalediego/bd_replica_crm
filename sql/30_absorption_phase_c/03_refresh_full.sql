CREATE OR REPLACE PROCEDURE analytics.refresh_absorption_phase_c_full()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE TABLE
        analytics.fact_absorcion_proyecto_diario,
        analytics.fact_stock_ofertado_diario,
        analytics.agg_ventas_mensual,
        analytics.fact_ventas_detalle,
        analytics.dim_periodo_comercial_proyecto,
        analytics.dim_fecha;


    -------------------------------------------------------------------------
    -- 0. Dimensión fecha PostgreSQL.
    -------------------------------------------------------------------------
    INSERT INTO analytics.dim_fecha(
        fecha,anio,trimestre,mes_numero,mes_nombre,periodo_mes,
        dia_mes,dia_semana_numero,dia_semana_nombre,es_fin_semana
    )
    SELECT
        d::date,
        extract(year from d)::int,
        extract(quarter from d)::int,
        extract(month from d)::int,
        trim(to_char(d,'TMMonth')),
        date_trunc('month',d)::date,
        extract(day from d)::int,
        extract(isodow from d)::int,
        trim(to_char(d,'TMDay')),
        extract(isodow from d)::int IN (6,7)
    FROM generate_series(
        (
            SELECT coalesce(min(fecha_evento),DATE '2018-01-01')
            FROM analytics.fact_movimientos_stock
        )::timestamp,
        current_date::timestamp,
        interval '1 day'
    ) d;

    -------------------------------------------------------------------------
    -- 1. Ventas canónicas.
    -------------------------------------------------------------------------
    INSERT INTO analytics.fact_ventas_detalle(
        sale_key,
        codigo_proforma,codigo_unidad,codigo_proyecto,
        separacion_source_id,venta_source_id,datos_extras_fecha_minuta_id,
        fecha_entrada_stock,fecha_separacion_raw,fecha_separacion,
        fecha_firma_legacy,fecha_de_minuta,
        fecha_venta_documental,fecha_venta,metodo_fecha_venta,
        primera_fecha_caida,
        resultado_documental,resultado_inventario,resultado_canonico,
        reconciliation_status,confidence_level,
        documento_cliente,asesor,tipo_unidad_principal,
        dias_separacion_venta
    )
    SELECT
        md5(c.codigo_proforma || '|' || c.codigo_unidad),
        c.codigo_proforma,
        c.codigo_unidad,
        c.codigo_proyecto,

        c.separacion_source_id,
        c.venta_source_id,
        c.datos_extras_fecha_minuta_id,

        c.fecha_entrada_stock,
        c.fecha_separacion_raw,
        c.fecha_separacion,
        c.fecha_firma_legacy,
        c.fecha_de_minuta,
        c.fecha_venta_documental,
        c.fecha_venta_validada,
        c.metodo_fecha_venta,
        c.primera_fecha_caida,

        c.resultado_ciclo,
        c.resultado_inventario,
        c.resultado_canonico,
        c.reconciliation_status,
        c.confidence_level,

        c.documento_cliente,
        c.asesor,
        c.tipo_unidad_principal,
        c.fecha_venta_validada - c.fecha_separacion
    FROM analytics.v_ciclo_comercial_reconciliado c
    WHERE c.resultado_canonico='VENTA'
      AND c.fecha_venta_validada IS NOT NULL
      AND c.reconciliation_status='RECONCILED';

    -------------------------------------------------------------------------
    -- 2. Periodo comercial observado del proyecto.
    -------------------------------------------------------------------------
    INSERT INTO analytics.dim_periodo_comercial_proyecto(
        codigo_proyecto,nombre_proyecto,fecha_inicio_venta_declarada,
        fecha_inicio_comercial_observada,
        fecha_ultima_actividad_comercial_observada,
        metodo_inicio_observado
    )
    WITH activity AS (
        SELECT
            pu.codigo_proyecto::text AS codigo_proyecto,
            min(pu.fecha_creacion::date) AS min_fecha,
            max(pu.fecha_creacion::date) AS max_fecha
        FROM raw_cygnus.proforma_unidad pu
        WHERE pu.codigo_proyecto IS NOT NULL
          AND pu.fecha_creacion IS NOT NULL
        GROUP BY pu.codigo_proyecto
    )
    SELECT
        p.codigo::text,
        p.nombre::text,
        p.fecha_inicio_venta::date,
        a.min_fecha,
        a.max_fecha,
        'PROFORMA_UNIDAD_FECHA_CREACION'
    FROM raw_cygnus.proyectos p
    LEFT JOIN activity a
      ON a.codigo_proyecto=p.codigo::text
    WHERE p.codigo IS NOT NULL;

    -------------------------------------------------------------------------
    -- 3. Stock diario a nivel proyecto.
    --
    -- NO unidades × calendario.
    -- Solo proyecto × rango de días observado.
    -------------------------------------------------------------------------
    WITH project_bounds AS (
        SELECT
            codigo_proyecto,
            min(fecha_evento) AS min_fecha,
            greatest(max(fecha_evento),current_date) AS max_fecha
        FROM analytics.fact_movimientos_stock
        WHERE codigo_proyecto IS NOT NULL
          AND transition_applied
        GROUP BY codigo_proyecto
    ),
    calendar AS (
        SELECT
            b.codigo_proyecto,
            gs::date AS fecha
        FROM project_bounds b
        CROSS JOIN LATERAL generate_series(
            b.min_fecha::timestamp,
            b.max_fecha::timestamp,
            interval '1 day'
        ) gs
    ),
    daily_move AS (
        SELECT
            codigo_proyecto,
            fecha_evento AS fecha,

            count(*) FILTER (
                WHERE tipo_evento='ALTA_STOCK'
                  AND transition_applied
            ) AS altas,

            count(*) FILTER (
                WHERE tipo_evento='SEPARACION'
                  AND transition_applied
            ) AS separaciones,

            count(*) FILTER (
                WHERE tipo_evento='CAIDA'
                  AND transition_applied
            ) AS caidas,

            count(*) FILTER (
                WHERE tipo_evento='VENTA'
                  AND transition_applied
            ) AS ventas,

            sum(delta_stock) FILTER (
                WHERE transition_applied
            ) AS delta_stock,

            sum(delta_separadas_activas) FILTER (
                WHERE transition_applied
            ) AS delta_separadas,

            sum(delta_ventas) FILTER (
                WHERE transition_applied
            ) AS delta_ventas

        FROM analytics.fact_movimientos_stock
        WHERE codigo_proyecto IS NOT NULL
        GROUP BY codigo_proyecto,fecha_evento
    ),
    x AS (
        SELECT
            cal.fecha,
            cal.codigo_proyecto,
            coalesce(m.altas,0)::bigint AS altas,
            coalesce(m.separaciones,0)::bigint AS separaciones,
            coalesce(m.caidas,0)::bigint AS caidas,
            coalesce(m.ventas,0)::bigint AS ventas,
            coalesce(m.delta_stock,0)::bigint AS delta_stock,
            coalesce(m.delta_separadas,0)::bigint AS delta_separadas,
            coalesce(m.delta_ventas,0)::bigint AS delta_ventas
        FROM calendar cal
        LEFT JOIN daily_move m
          ON m.codigo_proyecto=cal.codigo_proyecto
         AND m.fecha=cal.fecha
    ),
    running AS (
        SELECT
            x.*,
            sum(delta_stock) OVER (
                PARTITION BY codigo_proyecto
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS stock_fin,

            sum(delta_separadas) OVER (
                PARTITION BY codigo_proyecto
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS separadas_activas,

            sum(delta_ventas) OVER (
                PARTITION BY codigo_proyecto
                ORDER BY fecha
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )::bigint AS vendidas_acumuladas
        FROM x
    )
    INSERT INTO analytics.fact_stock_ofertado_diario(
        fecha,codigo_proyecto,
        stock_inicio,altas,separaciones,caidas_reingresadas,retiros,ventas,
        delta_stock,stock_fin,separadas_activas,vendidas_acumuladas
    )
    SELECT
        fecha,
        codigo_proyecto,
        (stock_fin - delta_stock)::bigint AS stock_inicio,
        altas,
        separaciones,
        caidas,
        0,
        ventas,
        delta_stock,
        stock_fin,
        separadas_activas,
        vendidas_acumuladas
    FROM running;

    -------------------------------------------------------------------------
    -- 4. Agregado mensual canónico.
    -------------------------------------------------------------------------
    WITH m AS (
        SELECT
            date_trunc('month',fecha_evento)::date AS periodo_mes,
            codigo_proyecto,
            count(*) FILTER (
                WHERE tipo_evento='SEPARACION' AND transition_applied
            ) AS separaciones,
            count(*) FILTER (
                WHERE tipo_evento='CAIDA' AND transition_applied
            ) AS caidas
        FROM analytics.fact_movimientos_stock
        WHERE codigo_proyecto IS NOT NULL
        GROUP BY 1,2
    ),
    v AS (
        SELECT
            date_trunc('month',fecha_venta)::date AS periodo_mes,
            codigo_proyecto,
            count(*) AS ventas
        FROM analytics.fact_ventas_detalle
        WHERE codigo_proyecto IS NOT NULL
        GROUP BY 1,2
    ),
    keys AS (
        SELECT periodo_mes,codigo_proyecto FROM m
        UNION
        SELECT periodo_mes,codigo_proyecto FROM v
    )
    INSERT INTO analytics.agg_ventas_mensual(
        periodo_mes,codigo_proyecto,
        separaciones_brutas,caidas,separaciones_netas,ventas,
        conversion_sep_venta,tasa_caida
    )
    SELECT
        k.periodo_mes,
        k.codigo_proyecto,
        coalesce(m.separaciones,0),
        coalesce(m.caidas,0),
        coalesce(m.separaciones,0)-coalesce(m.caidas,0),
        coalesce(v.ventas,0),

        coalesce(v.ventas,0)::numeric
            / nullif(coalesce(m.separaciones,0),0),

        coalesce(m.caidas,0)::numeric
            / nullif(coalesce(m.separaciones,0),0)

    FROM keys k
    LEFT JOIN m USING(periodo_mes,codigo_proyecto)
    LEFT JOIN v USING(periodo_mes,codigo_proyecto);

    -------------------------------------------------------------------------
    -- 5. Absorción diaria por proyecto.
    -------------------------------------------------------------------------
    WITH base AS (
        SELECT
            s.*,

            sum(s.separaciones) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS sep_7d,

            sum(s.caidas_reingresadas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS caida_7d,

            sum(s.ventas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS ventas_7d,

            lag(s.stock_fin,7) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
            ) AS stock_start_7d,

            sum(s.separaciones) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS sep_30d,

            sum(s.caidas_reingresadas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS caida_30d,

            sum(s.ventas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) AS ventas_30d,

            lag(s.stock_fin,30) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
            ) AS stock_start_30d,

            sum(s.separaciones) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS sep_90d,

            sum(s.caidas_reingresadas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS caida_90d,

            sum(s.ventas) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
                ROWS BETWEEN 89 PRECEDING AND CURRENT ROW
            ) AS ventas_90d,

            lag(s.stock_fin,90) OVER (
                PARTITION BY s.codigo_proyecto
                ORDER BY s.fecha
            ) AS stock_start_90d

        FROM analytics.fact_stock_ofertado_diario s
    ),
    cycle_daily AS (
        SELECT
            d.fecha,
            d.codigo_proyecto,

            (
                avg(c.dias_separacion_venta)
                FILTER (
                    WHERE c.resultado_canonico='VENTA'
                      AND c.fecha_venta_validada BETWEEN d.fecha - 29 AND d.fecha
                )
            )::numeric AS avg_sep_venta_30d,

            (
                avg(c.primera_fecha_caida - c.fecha_separacion)
                FILTER (
                    WHERE c.resultado_canonico='CAIDA'
                      AND c.primera_fecha_caida BETWEEN d.fecha - 29 AND d.fecha
                )
            )::numeric AS avg_sep_caida_30d

        FROM (
            SELECT DISTINCT fecha,codigo_proyecto
            FROM analytics.fact_stock_ofertado_diario
        ) d
        LEFT JOIN analytics.v_ciclo_comercial_reconciliado c
          ON c.codigo_proyecto=d.codigo_proyecto
         AND (
              c.fecha_venta_validada BETWEEN d.fecha - 29 AND d.fecha
              OR c.primera_fecha_caida BETWEEN d.fecha - 29 AND d.fecha
         )
        GROUP BY d.fecha,d.codigo_proyecto
    )
    INSERT INTO analytics.fact_absorcion_proyecto_diario(
        fecha,codigo_proyecto,
        stock_inicio,stock_fin,stock_promedio,
        separaciones_brutas,caidas,separaciones_netas,ventas,

        separaciones_brutas_7d,caidas_7d,separaciones_netas_7d,ventas_7d,
        stock_inicio_ventana_7d,absorcion_bruta_7d,absorcion_neta_7d,

        separaciones_brutas_30d,caidas_30d,separaciones_netas_30d,ventas_30d,
        stock_inicio_ventana_30d,absorcion_bruta_30d,absorcion_neta_30d,

        separaciones_brutas_90d,caidas_90d,separaciones_netas_90d,ventas_90d,
        stock_inicio_ventana_90d,absorcion_bruta_90d,absorcion_neta_90d,

        conversion_sep_venta_30d,tasa_caida_30d,
        dias_promedio_sep_venta_30d,dias_promedio_sep_caida_30d,
        velocidad_venta_diaria_30d,meses_stock_ventas_30d
    )
    SELECT
        b.fecha,
        b.codigo_proyecto,

        b.stock_inicio,
        b.stock_fin,
        (b.stock_inicio+b.stock_fin)::numeric/2,

        b.separaciones,
        b.caidas_reingresadas,
        b.separaciones-b.caidas_reingresadas,
        b.ventas,

        b.sep_7d,
        b.caida_7d,
        b.sep_7d-b.caida_7d,
        b.ventas_7d,
        b.stock_start_7d,
        b.sep_7d::numeric/nullif(b.stock_start_7d,0),
        (b.sep_7d-b.caida_7d)::numeric/nullif(b.stock_start_7d,0),

        b.sep_30d,
        b.caida_30d,
        b.sep_30d-b.caida_30d,
        b.ventas_30d,
        b.stock_start_30d,
        b.sep_30d::numeric/nullif(b.stock_start_30d,0),
        (b.sep_30d-b.caida_30d)::numeric/nullif(b.stock_start_30d,0),

        b.sep_90d,
        b.caida_90d,
        b.sep_90d-b.caida_90d,
        b.ventas_90d,
        b.stock_start_90d,
        b.sep_90d::numeric/nullif(b.stock_start_90d,0),
        (b.sep_90d-b.caida_90d)::numeric/nullif(b.stock_start_90d,0),

        b.ventas_30d::numeric/nullif(b.sep_30d,0),
        b.caida_30d::numeric/nullif(b.sep_30d,0),

        cd.avg_sep_venta_30d,
        cd.avg_sep_caida_30d,

        b.ventas_30d::numeric/30,
        b.stock_fin::numeric/nullif(b.ventas_30d,0)

    FROM base b
    LEFT JOIN cycle_daily cd
      ON cd.fecha=b.fecha
     AND cd.codigo_proyecto=b.codigo_proyecto;

    CALL analytics.run_absorption_phase_c_qa();
END;
$$;
