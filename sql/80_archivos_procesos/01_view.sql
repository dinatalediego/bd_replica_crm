CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.archivos_procesos AS
WITH pattern_config AS (
    SELECT
        ARRAY[
            'convenio de separacion',
            'convenio separacion',
            'convenio'
        ]::text[] AS convenio_separacion,
        ARRAY[
            'carta de aprobacion',
            'carta aprobacion',
            'pendiente de carta',
            'carta'
        ]::text[] AS carta_aprobacion,
        ARRAY[
            'minuta',
            'contrato de compraventa',
            'contrato compraventa',
            'compraventa',
            'contrato'
        ]::text[] AS contrato_minuta
),
filtered AS (
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
),
classified AS (
    SELECT
        f.*,
        n.nombre_normalizado,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM unnest(pc.convenio_separacion) AS p(patron)
                WHERE position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_convenio_separacion,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM unnest(pc.carta_aprobacion) AS p(patron)
                WHERE position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_carta_aprobacion,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM unnest(pc.contrato_minuta) AS p(patron)
                WHERE position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_contrato_minuta,
        n.montaje_normalizado
    FROM flags f
    CROSS JOIN pattern_config pc
    CROSS JOIN LATERAL (
        SELECT
            btrim(
                regexp_replace(
                    translate(
                        lower(coalesce(f.nombre::text, '')),
                        'áéíóúüñ',
                        'aeiouun'
                    ),
                    '[^a-z0-9]+',
                    ' ',
                    'g'
                )
            ) AS nombre_normalizado,
            lower(btrim(coalesce(f.montaje::text, ''))) AS montaje_normalizado
    ) n
),
typed AS (
    SELECT
        c.*,
        CASE
            WHEN c.montaje_normalizado <> 'contrato' THEN NULL
            WHEN (
                c.es_convenio_separacion::int
                + c.es_carta_aprobacion::int
                + c.es_contrato_minuta::int
            ) <> 1 THEN 'incierto'
            WHEN c.es_convenio_separacion THEN 'Convenio de Separacion'
            WHEN c.es_carta_aprobacion THEN 'carta de aprobacion'
            WHEN c.es_contrato_minuta THEN 'contrato o minuta'
            ELSE 'incierto'
        END AS tipo_contrato_archivo
    FROM classified c
)
SELECT
    t.*,
    row_number() OVER (
        PARTITION BY btrim(t.codigo_proforma::text)
        ORDER BY t.fecha_carga ASC NULLS LAST, t.entidad_id DESC NULLS LAST
    )::bigint AS "Rank",
    CASE
        WHEN t.montaje_normalizado = 'contrato'
        THEN count(*) FILTER (
            WHERE t.montaje_normalizado = 'contrato'
        ) OVER (
            PARTITION BY btrim(t.codigo_proforma::text)
            ORDER BY t.fecha_carga ASC NULLS LAST, t.entidad_id DESC NULLS LAST
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint
        ELSE NULL
    END AS ranking_contrato,
    CASE
        WHEN t.montaje_normalizado = 'proceso adquisicion'
        THEN count(*) FILTER (
            WHERE t.montaje_normalizado = 'proceso adquisicion'
        ) OVER (
            PARTITION BY btrim(t.codigo_proforma::text)
            ORDER BY t.fecha_carga ASC NULLS LAST, t.entidad_id DESC NULLS LAST
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::bigint
        ELSE NULL
    END AS ranking_pasos
FROM typed t;

COMMENT ON VIEW analytics.archivos_procesos IS
'Replica en PostgreSQL de la lógica Power Query archivos_procesos: filtra Proceso Adquisicion/Paso, marca regularizar.pdf, clasifica nombres de archivos de montaje Contrato y calcula Rank, ranking_contrato y ranking_pasos por codigo_proforma. La configuración inicial de patrones vive en el CTE pattern_config.';
