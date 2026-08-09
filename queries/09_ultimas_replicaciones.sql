-- ============================================================
-- MEDALLIO DW - ULTIMA REPLICACION POR TABLA
-- Requiere medallio_control.replication_runs
-- ============================================================

WITH ultimas AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY target_schema, target_table
            ORDER BY inicio_sync DESC
        ) AS rn
    FROM medallio_control.replication_runs r
)
SELECT
    target_schema AS esquema,
    target_table AS tabla,
    strategy,
    watermark_column,
    watermark_to AS ultimo_watermark,
    filas_extraidas,
    filas_insertadas,
    filas_actualizadas,
    filas_local_final,
    inicio_sync,
    fin_sync,
    duracion_seg,
    status,
    error_message
FROM ultimas
WHERE rn = 1
ORDER BY target_table;
