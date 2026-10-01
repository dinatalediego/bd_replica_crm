-- Una fila por departamento en una proforma con Separacion Activo.
-- Se cruzan documentos de titulares/copropietarios y proyecto; nunca solo nombres.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.v_propietarios_equipamiento AS
WITH separaciones AS (
    SELECT btrim(p.codigo_proforma::text) AS codigo_proforma,
           NULLIF(btrim(p.codigo_unidad::text), '') AS codigo_principal,
           p.codigo_unidades_asignadas::text AS adicionales,
           p.tipo_unidad_principal::text AS tipo_principal,
           p.documento_cliente::text AS titular,
           p.documento_copropietarios::text AS copropietarios,
           p.documento_conyuge::text AS conyuge
    FROM raw_cygnus.procesos p
    WHERE lower(btrim(p.nombre::text)) = 'separacion'
      AND lower(btrim(p.estado::text)) = 'activo'
      AND NULLIF(btrim(p.codigo_proforma::text), '') IS NOT NULL
),
participantes_raw AS (
    SELECT codigo_proforma, titular AS documento FROM separaciones
    UNION ALL
    SELECT s.codigo_proforma, x.documento
    FROM separaciones s
    CROSS JOIN LATERAL regexp_split_to_table(coalesce(s.copropietarios, ''), '[,;|]') AS x(documento)
    UNION ALL
    SELECT s.codigo_proforma, x.documento
    FROM separaciones s
    CROSS JOIN LATERAL regexp_split_to_table(coalesce(s.conyuge, ''), '[,;|]') AS x(documento)
),
participantes AS (
    SELECT DISTINCT codigo_proforma,
           nullif(regexp_replace(regexp_replace(btrim(documento), '\.0$', ''), '[^0-9]', '', 'g'), '') AS documento
    FROM participantes_raw
    WHERE documento IS NOT NULL
),
unidades_candidatas AS (
    SELECT s.codigo_proforma, s.codigo_principal AS codigo_unidad,
           s.tipo_principal AS tipo_hint
    FROM separaciones s
    WHERE s.codigo_principal IS NOT NULL
    UNION ALL
    SELECT s.codigo_proforma, btrim(x.codigo_unidad), NULL::text
    FROM separaciones s
    CROSS JOIN LATERAL regexp_split_to_table(coalesce(s.adicionales, ''), '[,;|]') AS x(codigo_unidad)
    WHERE btrim(x.codigo_unidad) <> ''
    UNION ALL
    SELECT btrim(pu.codigo_proforma::text), btrim(pu.codigo_unidad::text), NULL::text
    FROM raw_cygnus.proforma_unidad pu
    JOIN (SELECT DISTINCT codigo_proforma FROM separaciones) s
      ON s.codigo_proforma = btrim(pu.codigo_proforma::text)
    WHERE nullif(btrim(pu.codigo_unidad::text), '') IS NOT NULL
),
unidades_proforma AS (
    SELECT codigo_proforma, codigo_unidad,
           max(tipo_hint) AS tipo_hint
    FROM unidades_candidatas
    GROUP BY codigo_proforma, codigo_unidad
),
clasificadas AS (
    SELECT up.codigo_proforma, up.codigo_unidad,
           btrim(u.codigo_proyecto::text) AS codigo_proyecto,
           lower(translate(
               coalesce(nullif(btrim(u.tipo_unidad::text), ''), up.tipo_hint, ''),
               'ÁÉÍÓÚÜáéíóúü', 'AEIOUUaeiouu'
           )) AS tipo
    FROM unidades_proforma up
    JOIN raw_cygnus.unidades u
      ON btrim(u.codigo::text) = up.codigo_unidad
    WHERE nullif(btrim(u.codigo_proyecto::text), '') IS NOT NULL
),
activos_por_persona AS (
    SELECT DISTINCT c.codigo_proyecto, p.documento, c.tipo
    FROM clasificadas c
    JOIN participantes p USING (codigo_proforma)
    WHERE p.documento IS NOT NULL
),
departamentos AS (
    SELECT DISTINCT codigo_proforma, codigo_unidad, codigo_proyecto
    FROM clasificadas
    WHERE (tipo LIKE '%departamento%' AND (tipo LIKE '%flat%' OR tipo LIKE '%duplex%'))
       OR tipo IN ('flat', 'duplex')
)
SELECT d.codigo_proforma, d.codigo_unidad, d.codigo_proyecto,
       EXISTS (
           SELECT 1
           FROM participantes p
           JOIN activos_por_persona a ON a.documento = p.documento
           WHERE p.codigo_proforma = d.codigo_proforma
             AND a.codigo_proyecto = d.codigo_proyecto
             AND (a.tipo LIKE '%estacionamiento%' OR a.tipo LIKE '%cochera%')
       ) AS tiene_cochera,
       EXISTS (
           SELECT 1
           FROM participantes p
           JOIN activos_por_persona a ON a.documento = p.documento
           WHERE p.codigo_proforma = d.codigo_proforma
             AND a.codigo_proyecto = d.codigo_proyecto
             AND a.tipo LIKE '%deposit%'
       ) AS tiene_deposito
FROM departamentos d;
