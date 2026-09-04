-- Semantic mart for Power BI unit analysis.
-- Replaces the heavy Power Query that UNIONs raw_cygnus.unidades + raw_mercado.unidades
-- and derives business flags in M.

CREATE SCHEMA IF NOT EXISTS analytics;

ALTER TABLE raw_mercado.unidades
    ADD COLUMN IF NOT EXISTS tipologia_ubicacion text;

UPDATE raw_mercado.unidades
SET tipologia_ubicacion = CASE
    WHEN NULLIF(TRIM(codigo), '') IS NULL THEN NULL
    ELSE RIGHT(TRIM(codigo), 2)
END
WHERE tipologia_ubicacion IS DISTINCT FROM CASE
    WHEN NULLIF(TRIM(codigo), '') IS NULL THEN NULL
    ELSE RIGHT(TRIM(codigo), 2)
END;

CREATE OR REPLACE VIEW analytics.unidades_powerbi AS
WITH base AS (
    SELECT
        'raw_cygnus'::text AS fuente_esquema,
        to_jsonb(u) AS j
    FROM raw_cygnus.unidades u

    UNION ALL

    SELECT
        'raw_mercado'::text AS fuente_esquema,
        to_jsonb(u) AS j
    FROM raw_mercado.unidades u
),
normalizada AS (
    SELECT
        fuente_esquema,
        NULLIF(TRIM(j->>'codigo'), '') AS codigo,
        j->>'nombre' AS nombre,
        NULLIF(TRIM(j->>'codigo_proyecto'), '') AS codigo_proyecto,
        j->>'nombre_proyecto' AS nombre_proyecto,
        j->>'codigo_subdivision' AS codigo_subdivision,
        j->>'nombre_subdivision' AS nombre_subdivision,
        j->>'tipo_unidad' AS tipo_unidad,
        j->>'piso' AS piso,
        j->>'estado_construccion' AS estado_construccion,
        j->>'nombre_tipologia' AS nombre_tipologia,
        COALESCE(NULLIF(TRIM(j->>'tipologia_ubicacion'), ''), RIGHT(NULLIF(TRIM(j->>'codigo'), ''), 2)) AS tipologia_ubicacion,
        j->>'total_habitaciones' AS total_habitaciones,
        j->>'total_banos' AS total_banos,
        j->>'area_libre' AS area_libre,
        j->>'area_techada' AS area_techada,
        j->>'area_total' AS area_total,
        j->>'estado_comercial' AS estado_comercial,
        j->>'estado_personalizado' AS estado_personalizado,
        j->>'codigo_proforma' AS codigo_proforma,
        j->>'precio_lista' AS precio_lista,
        j->>'precio_base_proforma' AS precio_base_proforma,
        j->>'descuento_venta' AS descuento_venta,
        j->>'precio_venta' AS precio_venta,
        j->>'precio_m2' AS precio_m2,
        j->>'fecha_reserva' AS fecha_reserva,
        j->>'fecha_separacion' AS fecha_separacion,
        j->>'fecha_venta' AS fecha_venta,
        j->>'fecha_entrega' AS fecha_entrega,
        j->>'modalidad_contrato' AS modalidad_contrato,
        j->>'codigo_externo' AS codigo_externo,
        j->>'id' AS id,
        j->>'padre_id' AS padre_id,
        j->>'_etl_loaded_at' AS _etl_loaded_at,
        j->>'_etl_source_run_id' AS _etl_source_run_id,
        CASE
            WHEN LOWER(TRIM(COALESCE(j->>'tipo_unidad',''))) IN (
                'departamento flat','departamento duplex','departamento triplex'
            ) THEN 1 ELSE 0
        END AS flag_departamento,
        CASE
            WHEN LOWER(TRIM(COALESCE(j->>'estado_comercial',''))) = 'no disponible' THEN 'no disponible'
            WHEN LOWER(TRIM(COALESCE(j->>'estado_comercial',''))) = 'disponible' THEN 'disponible'
            ELSE translate(LOWER(TRIM(COALESCE(j->>'estado_comercial',''))),'áéíóú','aeiou')
        END AS estado_comercial_normalizado
    FROM base
),
con_llave AS (
    SELECT
        *,
        CASE
            WHEN flag_departamento = 1
             AND codigo_proyecto IS NOT NULL
             AND NULLIF(TRIM(nombre_tipologia), '') IS NOT NULL
            THEN codigo_proyecto || '|' || TRIM(nombre_tipologia)
            ELSE NULL
        END AS llave_tipologia
    FROM normalizada
    WHERE codigo IS NOT NULL
),
resumen AS (
    SELECT
        codigo_proyecto,
        nombre_tipologia,
        COUNT(DISTINCT codigo)::bigint AS cantidad_unidades_tipologia
    FROM con_llave
    WHERE flag_departamento = 1
      AND llave_tipologia IS NOT NULL
    GROUP BY codigo_proyecto, nombre_tipologia
),
semantica AS (
    SELECT
        u.*,
        COALESCE(r.cantidad_unidades_tipologia, 0)::bigint AS cantidad_unidades_tipologia,
        CASE WHEN u.flag_departamento = 1 AND COALESCE(r.cantidad_unidades_tipologia,0) = 1 THEN 1 ELSE 0 END AS flag_tipologia_unidad_unica,
        CASE WHEN u.flag_departamento = 1 AND COALESCE(r.cantidad_unidades_tipologia,0) > 1 THEN 1 ELSE 0 END AS flag_tipologia_varias_unidades,
        CASE
            WHEN u.flag_departamento = 0 THEN 'No es departamento'
            WHEN u.llave_tipologia IS NULL THEN 'Departamento sin tipología'
            WHEN COALESCE(r.cantidad_unidades_tipologia,0) = 1 THEN 'Tipología de unidad única'
            WHEN COALESCE(r.cantidad_unidades_tipologia,0) > 1 THEN 'Tipología de varias unidades'
            ELSE 'Sin clasificación'
        END AS clasificacion_tipologia,
        CASE
            WHEN u.estado_comercial_normalizado = 'no disponible' THEN 'Bloqueado'
            WHEN u.estado_comercial_normalizado = 'disponible' THEN 'Disponible'
            WHEN u.estado_comercial_normalizado IN ('proceso de separacion','separado') THEN 'Separado'
            WHEN u.estado_comercial_normalizado IN ('proceso de aprobacion','proceso de venta','vendido') THEN 'Vendido'
            ELSE 'Sin clasificar'
        END AS estado
    FROM con_llave u
    LEFT JOIN resumen r
      ON r.codigo_proyecto = u.codigo_proyecto
     AND r.nombre_tipologia = u.nombre_tipologia
)
SELECT
    *,
    (estado_comercial_normalizado = 'no disponible') AS flag_estado_no_disponible,
    (estado_comercial_normalizado = 'disponible') AS flag_estado_disponible,
    (estado_comercial_normalizado = 'proceso de separacion') AS flag_estado_proceso_separacion,
    (estado_comercial_normalizado = 'separado') AS flag_estado_separado,
    (estado_comercial_normalizado = 'proceso de aprobacion') AS flag_estado_proceso_aprobacion,
    (estado_comercial_normalizado = 'proceso de venta') AS flag_estado_proceso_venta,
    (estado_comercial_normalizado = 'vendido') AS flag_estado_vendido,
    (estado = 'Bloqueado') AS flag_bloqueado,
    (estado = 'Disponible') AS flag_disponible,
    (estado = 'Separado') AS flag_separado,
    (estado = 'Vendido') AS flag_vendido,
    CASE estado
        WHEN 'Bloqueado' THEN 1
        WHEN 'Disponible' THEN 2
        WHEN 'Separado' THEN 3
        WHEN 'Vendido' THEN 4
        ELSE 99
    END AS orden_estado
FROM semantica;
