-- ============================================================
-- MEDALLIO DW - DASHBOARD SQL DE CONTROL
-- Combina estado físico local + última ejecución registrada.
-- Requiere medallio_control.replication_runs.
-- ============================================================

WITH tablas AS (
    SELECT
        s.schemaname AS esquema,
        s.relname AS tabla,
        s.n_live_tup AS filas_estimadas,
        s.n_dead_tup AS filas_muertas,
        pg_total_relation_size(
            quote_ident(s.schemaname) || '.' || quote_ident(s.relname)
        ) AS bytes_total,
        s.last_analyze,
        s.last_autoanalyze
    FROM pg_stat_user_tables s
    WHERE s.schemaname = 'raw_cygnus'
      AND s.relname IN (
          'clientes_proyectos',
          'interacciones',
          'clientes',
          'procesos',
          'proformas',
          'unidades'
      )
),
ultima_sync AS (
    SELECT *
    FROM (
        SELECT
            r.*,
            ROW_NUMBER() OVER (
                PARTITION BY target_schema, target_table
                ORDER BY inicio_sync DESC
            ) AS rn
        FROM medallio_control.replication_runs r
    ) x
    WHERE rn = 1
)
SELECT
    t.esquema,
    t.tabla,
    t.filas_estimadas,
    t.filas_muertas,
    pg_size_pretty(t.bytes_total) AS tamano_total,

    (
        SELECT COUNT(*)
        FROM information_schema.columns c
        WHERE c.table_schema = t.esquema
          AND c.table_name = t.tabla
    ) AS columnas,

    u.strategy,
    u.watermark_column,
    u.watermark_to AS ultimo_watermark,
    u.filas_extraidas,
    u.filas_insertadas,
    u.filas_actualizadas,
    u.inicio_sync,
    u.fin_sync,
    u.duracion_seg,
    COALESCE(u.status, 'SIN REGISTRO') AS status,

    CASE
        WHEN u.status = 'ERROR' THEN 'ERROR'
        WHEN u.status IS NULL THEN 'SIN AUDITORIA'
        WHEN u.fin_sync IS NULL THEN 'EN EJECUCION / INCOMPLETO'
        ELSE 'OK'
    END AS estado_control

FROM tablas t
LEFT JOIN ultima_sync u
    ON u.target_schema = t.esquema
   AND u.target_table = t.tabla
ORDER BY t.tabla;
