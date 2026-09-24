CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.archivos_procesos AS
WITH filtered AS (
    SELECT
        a.*
    FROM raw_cygnus.archivos a
    WHERE lower(btrim(coalesce(a.entidad::text, ''))) IN ('proceso adquisicion', 'paso')
      AND btrim(coalesce(a.codigo_proforma::text, '')) <> ''
),
enriched AS (
    SELECT
        f.*,
        (
            lower(btrim(coalesce(f.nombre::text, ''))) = 'regularizar.pdf'
        ) AS papel_blanco
    FROM filtered f
),
flags AS (
    SELECT
        e.*,
        (
            lower(btrim(coalesce(e.entidad::text, ''))) = 'proceso adquisicion'
            AND e.papel_blanco
        ) AS contrato_con_papel_blanco,
        bool_or(
            lower(btrim(coalesce(e.entidad::text, ''))) = 'paso'
            AND e.papel_blanco
        ) OVER (
            PARTITION BY btrim(e.codigo_proforma::text)
        ) AS tiene_pasos_en_blanco
    FROM enriched e
)
SELECT
    f.*,
    row_number() OVER (
        PARTITION BY btrim(f.codigo_proforma::text)
        ORDER BY f.fecha_carga ASC NULLS LAST, f.entidad_id DESC NULLS LAST
    )::bigint AS "Rank",
    CASE
        WHEN lower(btrim(coalesce(f.montaje::text, ''))) = 'contrato'
        THEN count(*) FILTER (
            WHERE lower(btrim(coalesce(f.montaje::text, ''))) = 'contrato'
        ) OVER (
            PARTITION BY btrim(f.codigo_proforma::text)
            ORDER BY f.fecha_carga ASC NULLS LAST, f.entidad_id DESC NULLS LAST
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint
        ELSE NULL
    END AS ranking_contrato,
    CASE
        WHEN lower(btrim(coalesce(f.montaje::text, ''))) = 'proceso adquisicion'
        THEN count(*) FILTER (
            WHERE lower(btrim(coalesce(f.montaje::text, ''))) = 'proceso adquisicion'
        ) OVER (
            PARTITION BY btrim(f.codigo_proforma::text)
            ORDER BY f.fecha_carga ASC NULLS LAST, f.entidad_id DESC NULLS LAST
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint
        ELSE NULL
    END AS ranking_pasos
FROM flags f;

COMMENT ON VIEW analytics.archivos_procesos IS
'Replica en PostgreSQL de la lógica Power Query archivos_procesos: filtra Proceso Adquisicion/Paso, marca regularizar.pdf y calcula Rank, ranking_contrato y ranking_pasos por codigo_proforma.';
