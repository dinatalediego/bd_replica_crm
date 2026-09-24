CREATE SCHEMA IF NOT EXISTS analytics;

-- Reglas configurables para clasificar el nombre de los archivos cuyo montaje es Contrato.
-- Los patrones se guardan normalizados (minúsculas, sin tildes ni signos).
CREATE TABLE IF NOT EXISTS analytics.archivos_contrato_patrones (
    tipo_contrato text NOT NULL,
    patron text NOT NULL,
    activo boolean NOT NULL DEFAULT true,
    prioridad smallint NOT NULL DEFAULT 100,
    descripcion text,
    PRIMARY KEY (tipo_contrato, patron),
    CONSTRAINT ck_archivos_contrato_patrones_tipo
        CHECK (
            tipo_contrato IN (
                'Convenio de Separacion',
                'carta de aprobacion',
                'contrato o minuta'
            )
        )
);

INSERT INTO analytics.archivos_contrato_patrones (
    tipo_contrato,
    patron,
    prioridad,
    descripcion
)
VALUES
    ('Convenio de Separacion', 'convenio de separacion', 10, 'Nombre explícito del convenio'),
    ('Convenio de Separacion', 'convenio separacion', 20, 'Variante sin preposición'),
    ('Convenio de Separacion', 'convenio', 90, 'Fallback observado en nombres abreviados'),

    ('carta de aprobacion', 'carta de aprobacion', 10, 'Nombre explícito de carta'),
    ('carta de aprobacion', 'carta aprobacion', 20, 'Variante abreviada'),
    ('carta de aprobacion', 'pendiente de carta', 30, 'Patrón observado en archivos reales'),
    ('carta de aprobacion', 'carta', 90, 'Fallback observado en nombres abreviados'),

    ('contrato o minuta', 'minuta', 10, 'Patrón observado en minutas'),
    ('contrato o minuta', 'contrato de compraventa', 10, 'Contrato explícito'),
    ('contrato o minuta', 'contrato compraventa', 20, 'Variante abreviada'),
    ('contrato o minuta', 'compraventa', 30, 'Fallback de compraventa'),
    ('contrato o minuta', 'contrato', 90, 'Fallback genérico de contrato')
ON CONFLICT (tipo_contrato, patron) DO NOTHING;

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
),
normalized AS (
    SELECT
        f.*,
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
    FROM flags f
),
classified AS (
    SELECT
        n.*,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM analytics.archivos_contrato_patrones p
                WHERE p.activo
                  AND p.tipo_contrato = 'Convenio de Separacion'
                  AND position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_convenio_separacion,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM analytics.archivos_contrato_patrones p
                WHERE p.activo
                  AND p.tipo_contrato = 'carta de aprobacion'
                  AND position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_carta_aprobacion,
        (
            n.montaje_normalizado = 'contrato'
            AND EXISTS (
                SELECT 1
                FROM analytics.archivos_contrato_patrones p
                WHERE p.activo
                  AND p.tipo_contrato = 'contrato o minuta'
                  AND position(p.patron in n.nombre_normalizado) > 0
            )
        ) AS es_contrato_minuta
    FROM normalized n
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

COMMENT ON TABLE analytics.archivos_contrato_patrones IS
'Patrones editables para clasificar archivos con montaje Contrato a partir de su nombre normalizado.';

COMMENT ON VIEW analytics.archivos_procesos IS
'Replica en PostgreSQL de la lógica Power Query archivos_procesos: filtra Proceso Adquisicion/Paso, marca regularizar.pdf, clasifica nombres de archivos de montaje Contrato y calcula Rank, ranking_contrato y ranking_pasos por codigo_proforma.';
