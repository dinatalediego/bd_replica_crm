"""Build LAL/RMKT audience marts from the local Medallio replica only."""

from __future__ import annotations

import argparse
import os

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


REQUIRED_RELATIONS = (
    "raw_cygnus.clientes",
    "raw_cygnus.clientes_proyectos",
    "raw_cygnus.procesos",
    "raw_cygnus.proformas",
    "raw_cygnus.proyectos",
    "staging.clientes_calidad",
    "analytics.marketing_audiencias",
    "analytics.marketing_audiencias_proyectos",
)


def validate_inactivity_days(value: int) -> int:
    if not 1 <= value <= 3650:
        raise ValueError("inactivity_days debe estar entre 1 y 3650")
    return value


BUILD_NEXT_SQL = r"""
CREATE TEMP TABLE marketing_audiencias_next ON COMMIT DROP AS
WITH project_dim AS (
    SELECT
        btrim(p.codigo::text) AS codigo_proyecto,
        NULLIF(btrim(p.nombre::text), '') AS nombre_proyecto
    FROM raw_cygnus.proyectos p
    WHERE NULLIF(btrim(p.codigo::text), '') IS NOT NULL
),
clientes AS (
    SELECT
        c.*,
        COALESCE(
            'doc:' || NULLIF(c.dq_documento_limpio, ''),
            'email:' || NULLIF(lower(c.dq_email_limpio), ''),
            'phone:' || NULLIF(c.dq_celular_limpio, ''),
            'source:' || NULLIF(c.source_id, ''),
            'hash:' || c.source_row_hash
        ) AS persona_key,
        CASE
            WHEN left(to_jsonb(r) ->> 'fecha_creacion', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN to_date(left(to_jsonb(r) ->> 'fecha_creacion', 10), 'YYYY-MM-DD')
        END AS fecha_cliente_crm
    FROM staging.clientes_calidad c
    LEFT JOIN raw_cygnus.clientes r
      ON r.id::text = c.source_id
),
cliente_keys AS (
    SELECT persona_key, 'source_id'::text AS key_type, source_id AS key_value
    FROM clientes WHERE NULLIF(source_id, '') IS NOT NULL
    UNION
    SELECT persona_key, 'documento', dq_documento_limpio
    FROM clientes WHERE NULLIF(dq_documento_limpio, '') IS NOT NULL
),
origen_base AS (
    SELECT
        cp.id::text AS source_row_id,
        NULLIF(regexp_replace(cp.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(cp) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(cp) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(cp) ->> 'codigo_cliente', '')
        ) AS source_id,
        NULLIF(btrim(cp.codigo_proyecto::text), '') AS codigo_proyecto,
        cp.fecha_creacion::date AS fecha_lead,
        NULLIF(
            regexp_replace(lower(btrim(COALESCE(cp.medio_captacion::text, ''))), '\s+', ' ', 'g'),
            ''
        ) AS medio_captacion
    FROM raw_cygnus.clientes_proyectos cp
    WHERE NULLIF(btrim(cp.codigo_proyecto::text), '') IS NOT NULL
),
origen_keys AS (
    SELECT source_row_id, 'source_id'::text AS key_type, source_id AS key_value
    FROM origen_base WHERE NULLIF(source_id, '') IS NOT NULL
    UNION ALL
    SELECT source_row_id, 'documento', documento
    FROM origen_base WHERE NULLIF(documento, '') IS NOT NULL
),
origen_evidence AS (
    SELECT DISTINCT
        ck.persona_key,
        ob.source_row_id,
        ob.codigo_proyecto,
        ob.fecha_lead,
        ob.medio_captacion
    FROM origen_keys ok
    JOIN cliente_keys ck
      ON ck.key_type = ok.key_type
     AND ck.key_value = ok.key_value
    JOIN origen_base ob
      ON ob.source_row_id = ok.source_row_id
),
origen_project AS (
    SELECT
        oe.persona_key,
        oe.codigo_proyecto,
        min(oe.fecha_lead) AS fecha_primer_lead,
        max(oe.fecha_lead) AS fecha_ultimo_lead,
        count(DISTINCT oe.source_row_id)::bigint AS cantidad_leads,
        (array_agg(oe.medio_captacion ORDER BY oe.fecha_lead NULLS LAST, oe.source_row_id)
            FILTER (WHERE oe.medio_captacion IS NOT NULL))[1] AS medio_primer_touch,
        (array_agg(oe.medio_captacion ORDER BY oe.fecha_lead DESC NULLS LAST, oe.source_row_id DESC)
            FILTER (WHERE oe.medio_captacion IS NOT NULL))[1] AS medio_ultimo_touch
    FROM origen_evidence oe
    GROUP BY oe.persona_key, oe.codigo_proyecto
),
origen_primary AS (
    SELECT DISTINCT ON (op.persona_key)
        op.persona_key,
        op.codigo_proyecto AS codigo_proyecto_origen,
        COALESCE(pd.nombre_proyecto, op.codigo_proyecto) AS proyecto_origen,
        op.fecha_primer_lead AS fecha_origen_primario,
        op.medio_primer_touch AS medio_captacion_origen
    FROM origen_project op
    LEFT JOIN project_dim pd USING (codigo_proyecto)
    ORDER BY
        op.persona_key,
        op.fecha_primer_lead NULLS LAST,
        op.codigo_proyecto
),
procesos_base AS (
    SELECT
        p.id::text AS source_row_id,
        NULLIF(regexp_replace(p.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(p) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(p) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(p) ->> 'codigo_cliente', '')
        ) AS source_id,
        p.fecha_inicio::timestamptz AS fecha_evento,
        translate(lower(btrim(p.nombre::text)), 'áéíóúñ', 'aeioun') AS nombre_evento,
        NULLIF(btrim(p.codigo_proforma::text), '') AS codigo_proforma,
        NULLIF(btrim(p.codigo_proyecto::text), '') AS codigo_proyecto,
        NULLIF(btrim(p.nombre_proyecto::text), '') AS nombre_proyecto
    FROM raw_cygnus.procesos p
),
proformas_base AS (
    SELECT
        p.id::text AS source_row_id,
        NULLIF(regexp_replace(COALESCE(
            to_jsonb(p) ->> 'documento_cliente',
            to_jsonb(p) ->> 'documento',
            to_jsonb(p) ->> 'numero_documento',
            ''
        ), '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(p) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(p) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(p) ->> 'codigo_cliente', '')
        ) AS source_id,
        CASE
            WHEN left(to_jsonb(p) ->> 'fecha_creacion', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN to_date(left(to_jsonb(p) ->> 'fecha_creacion', 10), 'YYYY-MM-DD')::timestamptz
        END AS fecha_evento,
        NULLIF(btrim(COALESCE(
            to_jsonb(p) ->> 'codigo_proyecto',
            to_jsonb(p) ->> 'proyecto_codigo',
            ''
        )), '') AS codigo_proyecto
    FROM raw_cygnus.proformas p
),
eventos AS (
    SELECT
        source_row_id,
        documento,
        source_id,
        CASE
            WHEN nombre_evento IN ('venta', 'minuta') THEN 3
            WHEN nombre_evento = 'separacion' THEN 2
            WHEN codigo_proforma IS NOT NULL THEN 1
            ELSE 0
        END AS nivel,
        fecha_evento,
        codigo_proyecto,
        nombre_proyecto,
        'PROCESO'::text AS fuente_evento
    FROM procesos_base
    WHERE nombre_evento IN ('venta', 'minuta', 'separacion')
       OR codigo_proforma IS NOT NULL

    UNION ALL

    SELECT
        source_row_id,
        documento,
        source_id,
        1,
        fecha_evento,
        codigo_proyecto,
        NULL::text,
        'PROFORMA'::text
    FROM proformas_base
),
evento_keys AS (
    SELECT
        source_row_id, fuente_evento, 'source_id'::text AS key_type, source_id AS key_value,
        nivel, fecha_evento, codigo_proyecto, nombre_proyecto
    FROM eventos
    WHERE NULLIF(source_id, '') IS NOT NULL

    UNION ALL

    SELECT
        source_row_id, fuente_evento, 'documento', documento,
        nivel, fecha_evento, codigo_proyecto, nombre_proyecto
    FROM eventos
    WHERE NULLIF(documento, '') IS NOT NULL
),
evento_evidence AS (
    SELECT DISTINCT
        ck.persona_key,
        ek.source_row_id,
        ek.fuente_evento,
        ek.nivel,
        ek.fecha_evento,
        ek.codigo_proyecto,
        ek.nombre_proyecto
    FROM evento_keys ek
    JOIN cliente_keys ck
      ON ck.key_type = ek.key_type
     AND ck.key_value = ek.key_value
),
avances AS (
    SELECT
        persona_key,
        max(nivel) AS nivel,
        min(fecha_evento) FILTER (WHERE nivel = 1) AS fecha_proforma,
        min(fecha_evento) FILTER (WHERE nivel = 2) AS fecha_separacion,
        min(fecha_evento) FILTER (WHERE nivel = 3) AS fecha_minuta_venta,
        max(fecha_evento) AS fecha_ultimo_avance
    FROM evento_evidence
    GROUP BY persona_key
),
proforma_primary AS (
    SELECT DISTINCT ON (ee.persona_key)
        ee.persona_key,
        ee.codigo_proyecto AS codigo_proyecto_proforma,
        COALESCE(pd.nombre_proyecto, ee.codigo_proyecto) AS proyecto_proforma
    FROM evento_evidence ee
    LEFT JOIN project_dim pd USING (codigo_proyecto)
    WHERE ee.fuente_evento = 'PROFORMA'
      AND ee.codigo_proyecto IS NOT NULL
    ORDER BY ee.persona_key, ee.fecha_evento NULLS LAST, ee.source_row_id
),
conversion_primary AS (
    SELECT DISTINCT ON (ee.persona_key)
        ee.persona_key,
        ee.codigo_proyecto AS codigo_proyecto_conversion,
        COALESCE(NULLIF(ee.nombre_proyecto, ''), pd.nombre_proyecto, ee.codigo_proyecto)
            AS proyecto_conversion
    FROM evento_evidence ee
    LEFT JOIN project_dim pd USING (codigo_proyecto)
    WHERE ee.fuente_evento = 'PROCESO'
      AND ee.nivel IN (2, 3)
      AND ee.codigo_proyecto IS NOT NULL
    ORDER BY
        ee.persona_key,
        ee.nivel DESC,
        ee.fecha_evento NULLS LAST,
        ee.source_row_id
),
ranked AS (
    SELECT
        c.*,
        COALESCE(a.nivel, 0) AS nivel,
        a.fecha_proforma,
        a.fecha_separacion,
        a.fecha_minuta_venta,
        a.fecha_ultimo_avance,
        row_number() OVER (
            PARTITION BY c.persona_key
            ORDER BY COALESCE(a.nivel, 0) DESC,
                     c.dq_score_cliente DESC,
                     c.refreshed_at DESC,
                     c.source_row_hash DESC
        ) AS rn
    FROM clientes c
    LEFT JOIN avances a USING (persona_key)
)
SELECT
    r.persona_key,
    r.source_id,
    COALESCE(NULLIF(r.nombres, ''), NULLIF(r.nombre, ''), r.dq_nombre_cliente) AS nombres,
    NULLIF(r.apellidos, '') AS apellidos,
    CASE WHEN r.dq_celular_ok THEN r.dq_celular_limpio END AS celular,
    CASE WHEN r.dq_email_ok THEN r.dq_email_limpio END AS email,

    COALESCE(op.medio_captacion_origen, r.dq_medio_captacion) AS medio_captacion,
    r.dq_medio_captacion AS medio_captacion_cliente,
    op.medio_captacion_origen,

    op.codigo_proyecto_origen,
    op.proyecto_origen,
    pp.codigo_proyecto_proforma,
    pp.proyecto_proforma,
    cp.codigo_proyecto_conversion,
    cp.proyecto_conversion,

    COALESCE(op.proyecto_origen, cp.proyecto_conversion, pp.proyecto_proforma, r.dq_proyecto)
        AS proyecto,
    CASE
        WHEN op.proyecto_origen IS NOT NULL THEN 'ORIGEN'
        WHEN cp.proyecto_conversion IS NOT NULL THEN 'CONVERSION'
        WHEN pp.proyecto_proforma IS NOT NULL THEN 'PROFORMA'
        WHEN r.dq_proyecto IS NOT NULL THEN 'CLIENTE'
        ELSE 'SIN_PROYECTO'
    END AS fuente_proyecto,

    (
        op.codigo_proyecto_origen IS NOT NULL
        AND COALESCE(cp.codigo_proyecto_conversion, pp.codigo_proyecto_proforma) IS NOT NULL
        AND op.codigo_proyecto_origen
            IS DISTINCT FROM COALESCE(cp.codigo_proyecto_conversion, pp.codigo_proyecto_proforma)
    ) AS cambio_proyecto,

    COALESCE(op.fecha_origen_primario, r.fecha_cliente_crm) AS fecha_cliente,
    r.fecha_cliente_crm,
    op.fecha_origen_primario,

    r.fecha_proforma,
    r.fecha_separacion,
    r.fecha_minuta_venta,
    r.fecha_ultimo_avance,

    CASE r.nivel
        WHEN 3 THEN 'minuta_venta'
        WHEN 2 THEN 'separacion'
        WHEN 1 THEN 'proforma'
        ELSE 'sin_avance'
    END AS etapa_maxima,

    (r.nivel > 0) AS positiva,

    (
        r.nivel = 0
        AND COALESCE(
            COALESCE(op.fecha_origen_primario, r.fecha_cliente_crm)
                <= current_date - %(inactivity_days)s,
            false
        )
    ) AS negativa_sin_avance,

    (r.nivel >= 3) AS exclusion_convertido,
    (NOT r.dq_contacto_valido_ok) AS exclusion_contacto_invalido,
    COALESCE(s.activo, false) AS exclusion_no_contactar,
    r.dq_contacto_valido_ok AS contacto_valido,

    COALESCE(
        c.permitido
        AND c.verificado_en <= now()
        AND (c.vence_en IS NULL OR c.vence_en > now()),
        false
    ) AS consentimiento_publicidad_verificado,

    (
        r.dq_contacto_valido_ok
        AND NOT COALESCE(s.activo, false)
        AND COALESCE(
            c.permitido
            AND c.verificado_en <= now()
            AND (c.vence_en IS NULL OR c.vence_en > now()),
            false
        )
    ) AS apto_entrega_externa,

    now() AS actualizado_en

FROM ranked r
LEFT JOIN origen_primary op USING (persona_key)
LEFT JOIN proforma_primary pp USING (persona_key)
LEFT JOIN conversion_primary cp USING (persona_key)
LEFT JOIN analytics.marketing_consentimientos c USING (persona_key)
LEFT JOIN analytics.marketing_supresiones s USING (persona_key)
WHERE r.rn = 1
"""


BUILD_PROJECTS_NEXT_SQL = r"""
CREATE TEMP TABLE marketing_audiencias_proyectos_next ON COMMIT DROP AS
WITH project_dim AS (
    SELECT
        btrim(p.codigo::text) AS codigo_proyecto,
        NULLIF(btrim(p.nombre::text), '') AS nombre_proyecto
    FROM raw_cygnus.proyectos p
    WHERE NULLIF(btrim(p.codigo::text), '') IS NOT NULL
),
clientes AS (
    SELECT
        c.*,
        COALESCE(
            'doc:' || NULLIF(c.dq_documento_limpio, ''),
            'email:' || NULLIF(lower(c.dq_email_limpio), ''),
            'phone:' || NULLIF(c.dq_celular_limpio, ''),
            'source:' || NULLIF(c.source_id, ''),
            'hash:' || c.source_row_hash
        ) AS persona_key
    FROM staging.clientes_calidad c
),
cliente_keys AS (
    SELECT persona_key, 'source_id'::text AS key_type, source_id AS key_value
    FROM clientes WHERE NULLIF(source_id, '') IS NOT NULL
    UNION
    SELECT persona_key, 'documento', dq_documento_limpio
    FROM clientes WHERE NULLIF(dq_documento_limpio, '') IS NOT NULL
),
origen_base AS (
    SELECT
        cp.id::text AS source_row_id,
        NULLIF(regexp_replace(cp.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(cp) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(cp) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(cp) ->> 'codigo_cliente', '')
        ) AS source_id,
        NULLIF(btrim(cp.codigo_proyecto::text), '') AS codigo_proyecto,
        cp.fecha_creacion::date AS fecha_lead,
        NULLIF(
            regexp_replace(lower(btrim(COALESCE(cp.medio_captacion::text, ''))), '\s+', ' ', 'g'),
            ''
        ) AS medio_captacion
    FROM raw_cygnus.clientes_proyectos cp
    WHERE NULLIF(btrim(cp.codigo_proyecto::text), '') IS NOT NULL
),
origen_keys AS (
    SELECT source_row_id, 'source_id'::text AS key_type, source_id AS key_value
    FROM origen_base WHERE NULLIF(source_id, '') IS NOT NULL
    UNION ALL
    SELECT source_row_id, 'documento', documento
    FROM origen_base WHERE NULLIF(documento, '') IS NOT NULL
),
origen_evidence AS (
    SELECT DISTINCT
        ck.persona_key,
        ob.source_row_id,
        ob.codigo_proyecto,
        ob.fecha_lead,
        ob.medio_captacion
    FROM origen_keys ok
    JOIN cliente_keys ck
      ON ck.key_type = ok.key_type
     AND ck.key_value = ok.key_value
    JOIN origen_base ob
      ON ob.source_row_id = ok.source_row_id
),
origen_project AS (
    SELECT
        oe.persona_key,
        oe.codigo_proyecto,
        min(oe.fecha_lead) AS fecha_primer_lead,
        max(oe.fecha_lead) AS fecha_ultimo_lead,
        count(DISTINCT oe.source_row_id)::bigint AS cantidad_leads,
        (array_agg(oe.medio_captacion ORDER BY oe.fecha_lead NULLS LAST, oe.source_row_id)
            FILTER (WHERE oe.medio_captacion IS NOT NULL))[1] AS medio_primer_touch,
        (array_agg(oe.medio_captacion ORDER BY oe.fecha_lead DESC NULLS LAST, oe.source_row_id DESC)
            FILTER (WHERE oe.medio_captacion IS NOT NULL))[1] AS medio_ultimo_touch
    FROM origen_evidence oe
    GROUP BY oe.persona_key, oe.codigo_proyecto
),
proformas_base AS (
    SELECT
        p.id::text AS source_row_id,
        NULLIF(regexp_replace(COALESCE(
            to_jsonb(p) ->> 'documento_cliente',
            to_jsonb(p) ->> 'documento',
            to_jsonb(p) ->> 'numero_documento',
            ''
        ), '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(p) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(p) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(p) ->> 'codigo_cliente', '')
        ) AS source_id,
        CASE
            WHEN left(to_jsonb(p) ->> 'fecha_creacion', 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN to_date(left(to_jsonb(p) ->> 'fecha_creacion', 10), 'YYYY-MM-DD')::timestamptz
        END AS fecha_evento,
        NULLIF(btrim(COALESCE(
            to_jsonb(p) ->> 'codigo_proyecto',
            to_jsonb(p) ->> 'proyecto_codigo',
            ''
        )), '') AS codigo_proyecto
    FROM raw_cygnus.proformas p
),
proforma_keys AS (
    SELECT source_row_id, 'source_id'::text AS key_type, source_id AS key_value,
           fecha_evento, codigo_proyecto
    FROM proformas_base
    WHERE NULLIF(source_id, '') IS NOT NULL

    UNION ALL

    SELECT source_row_id, 'documento', documento, fecha_evento, codigo_proyecto
    FROM proformas_base
    WHERE NULLIF(documento, '') IS NOT NULL
),
proforma_evidence AS (
    SELECT DISTINCT
        ck.persona_key,
        pk.source_row_id,
        pk.codigo_proyecto,
        pk.fecha_evento
    FROM proforma_keys pk
    JOIN cliente_keys ck
      ON ck.key_type = pk.key_type
     AND ck.key_value = pk.key_value
    WHERE pk.codigo_proyecto IS NOT NULL
),
proforma_project AS (
    SELECT
        persona_key,
        codigo_proyecto,
        min(fecha_evento) AS fecha_primera_proforma
    FROM proforma_evidence
    GROUP BY persona_key, codigo_proyecto
),
procesos_base AS (
    SELECT
        p.id::text AS source_row_id,
        NULLIF(regexp_replace(p.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(p) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(p) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(p) ->> 'codigo_cliente', '')
        ) AS source_id,
        p.fecha_inicio::timestamptz AS fecha_evento,
        translate(lower(btrim(p.nombre::text)), 'áéíóúñ', 'aeioun') AS nombre_evento,
        NULLIF(btrim(p.codigo_proyecto::text), '') AS codigo_proyecto
    FROM raw_cygnus.procesos p
),
proceso_keys AS (
    SELECT
        source_row_id, 'source_id'::text AS key_type, source_id AS key_value,
        fecha_evento, nombre_evento, codigo_proyecto
    FROM procesos_base
    WHERE NULLIF(source_id, '') IS NOT NULL

    UNION ALL

    SELECT
        source_row_id, 'documento', documento, fecha_evento, nombre_evento, codigo_proyecto
    FROM procesos_base
    WHERE NULLIF(documento, '') IS NOT NULL
),
proceso_evidence AS (
    SELECT DISTINCT
        ck.persona_key,
        pk.source_row_id,
        pk.codigo_proyecto,
        pk.fecha_evento,
        pk.nombre_evento
    FROM proceso_keys pk
    JOIN cliente_keys ck
      ON ck.key_type = pk.key_type
     AND ck.key_value = pk.key_value
    WHERE pk.codigo_proyecto IS NOT NULL
      AND pk.nombre_evento IN ('separacion', 'venta', 'minuta')
),
proceso_project AS (
    SELECT
        persona_key,
        codigo_proyecto,
        min(fecha_evento) FILTER (WHERE nombre_evento = 'separacion') AS fecha_primera_separacion,
        min(fecha_evento) FILTER (WHERE nombre_evento IN ('venta', 'minuta'))
            AS fecha_primera_minuta_venta
    FROM proceso_evidence
    GROUP BY persona_key, codigo_proyecto
),
all_projects AS (
    SELECT persona_key, codigo_proyecto FROM origen_project
    UNION
    SELECT persona_key, codigo_proyecto FROM proforma_project
    UNION
    SELECT persona_key, codigo_proyecto FROM proceso_project
),
assembled AS (
    SELECT
        ap.persona_key,
        ap.codigo_proyecto,
        COALESCE(pd.nombre_proyecto, ap.codigo_proyecto) AS proyecto,
        op.fecha_primer_lead,
        op.fecha_ultimo_lead,
        op.medio_primer_touch AS medio_captacion_primer_touch,
        op.medio_ultimo_touch AS medio_captacion_ultimo_touch,
        COALESCE(op.cantidad_leads, 0)::bigint AS cantidad_leads,
        pf.fecha_primera_proforma,
        pr.fecha_primera_separacion,
        pr.fecha_primera_minuta_venta
    FROM all_projects ap
    JOIN marketing_audiencias_next ma USING (persona_key)
    LEFT JOIN project_dim pd USING (codigo_proyecto)
    LEFT JOIN origen_project op USING (persona_key, codigo_proyecto)
    LEFT JOIN proforma_project pf USING (persona_key, codigo_proyecto)
    LEFT JOIN proceso_project pr USING (persona_key, codigo_proyecto)
)
SELECT
    a.persona_key,
    a.codigo_proyecto,
    a.proyecto,
    a.fecha_primer_lead,
    a.fecha_ultimo_lead,
    a.medio_captacion_primer_touch,
    a.medio_captacion_ultimo_touch,
    a.cantidad_leads,
    (
        a.fecha_primer_lead IS NOT NULL
        AND a.fecha_primer_lead = min(a.fecha_primer_lead) OVER (PARTITION BY a.persona_key)
    ) AS es_primer_touch,
    (
        a.fecha_ultimo_lead IS NOT NULL
        AND a.fecha_ultimo_lead = max(a.fecha_ultimo_lead) OVER (PARTITION BY a.persona_key)
    ) AS es_ultimo_touch,
    (a.fecha_primera_proforma IS NOT NULL) AS tuvo_proforma,
    (a.fecha_primera_separacion IS NOT NULL) AS tuvo_separacion,
    (a.fecha_primera_minuta_venta IS NOT NULL) AS tuvo_minuta_venta,
    a.fecha_primera_proforma,
    a.fecha_primera_separacion,
    a.fecha_primera_minuta_venta,
    now() AS actualizado_en
FROM assembled a
"""


LOAD_AUDIENCES_SQL = r"""
INSERT INTO analytics.marketing_audiencias (
    persona_key, source_id, nombres, apellidos, celular, email,
    medio_captacion, medio_captacion_cliente, medio_captacion_origen,
    codigo_proyecto_origen, proyecto_origen,
    codigo_proyecto_proforma, proyecto_proforma,
    codigo_proyecto_conversion, proyecto_conversion,
    proyecto, fuente_proyecto, cambio_proyecto,
    fecha_cliente, fecha_cliente_crm, fecha_origen_primario,
    fecha_proforma, fecha_separacion, fecha_minuta_venta, fecha_ultimo_avance,
    etapa_maxima, positiva, negativa_sin_avance, exclusion_convertido,
    exclusion_contacto_invalido, exclusion_no_contactar, contacto_valido,
    consentimiento_publicidad_verificado, apto_entrega_externa, actualizado_en
)
SELECT
    persona_key, source_id, nombres, apellidos, celular, email,
    medio_captacion, medio_captacion_cliente, medio_captacion_origen,
    codigo_proyecto_origen, proyecto_origen,
    codigo_proyecto_proforma, proyecto_proforma,
    codigo_proyecto_conversion, proyecto_conversion,
    proyecto, fuente_proyecto, cambio_proyecto,
    fecha_cliente, fecha_cliente_crm, fecha_origen_primario,
    fecha_proforma, fecha_separacion, fecha_minuta_venta, fecha_ultimo_avance,
    etapa_maxima, positiva, negativa_sin_avance, exclusion_convertido,
    exclusion_contacto_invalido, exclusion_no_contactar, contacto_valido,
    consentimiento_publicidad_verificado, apto_entrega_externa, actualizado_en
FROM marketing_audiencias_next
"""


LOAD_PROJECTS_SQL = r"""
INSERT INTO analytics.marketing_audiencias_proyectos (
    persona_key, codigo_proyecto, proyecto,
    fecha_primer_lead, fecha_ultimo_lead,
    medio_captacion_primer_touch, medio_captacion_ultimo_touch,
    cantidad_leads, es_primer_touch, es_ultimo_touch,
    tuvo_proforma, tuvo_separacion, tuvo_minuta_venta,
    fecha_primera_proforma, fecha_primera_separacion, fecha_primera_minuta_venta,
    actualizado_en
)
SELECT
    persona_key, codigo_proyecto, proyecto,
    fecha_primer_lead, fecha_ultimo_lead,
    medio_captacion_primer_touch, medio_captacion_ultimo_touch,
    cantidad_leads, es_primer_touch, es_ultimo_touch,
    tuvo_proforma, tuvo_separacion, tuvo_minuta_venta,
    fecha_primera_proforma, fecha_primera_separacion, fecha_primera_minuta_venta,
    actualizado_en
FROM marketing_audiencias_proyectos_next
"""


def refresh(conn, *, inactivity_days: int = 180, timeout_seconds: int = 600) -> dict[str, int]:
    inactivity_days = validate_inactivity_days(inactivity_days)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser positivo")

    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('lock_timeout', '30s', true)")
            cur.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{timeout_seconds}s",),
            )
            for relation in REQUIRED_RELATIONS:
                cur.execute("SELECT to_regclass(%s)", (relation,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError(f"Falta relación requerida: {relation}")

            cur.execute("SELECT pg_try_advisory_xact_lock(9042026, 115)")
            if not cur.fetchone()[0]:
                raise RuntimeError("marketing_audiencias: otro refresh sigue activo")

            cur.execute(
                "LOCK TABLE analytics.marketing_audiencias, "
                "analytics.marketing_audiencias_proyectos IN SHARE ROW EXCLUSIVE MODE"
            )

            cur.execute("DROP TABLE IF EXISTS pg_temp.marketing_audiencias_next")
            cur.execute("DROP TABLE IF EXISTS pg_temp.marketing_audiencias_proyectos_next")

            cur.execute(BUILD_NEXT_SQL, {"inactivity_days": inactivity_days})
            cur.execute(BUILD_PROJECTS_NEXT_SQL)

            # Parent delete cascades to project lineage; both are reloaded atomically.
            cur.execute("DELETE FROM analytics.marketing_audiencias")
            cur.execute(LOAD_AUDIENCES_SQL)
            cur.execute(LOAD_PROJECTS_SQL)

            cur.execute("SELECT * FROM analytics.v_marketing_audiencias_health")
            columns = [item.name for item in cur.description]
            health = dict(zip(columns, cur.fetchone()))

            cur.execute("SELECT count(*) FROM staging.clientes_calidad")
            source_count = int(cur.fetchone()[0] or 0)
            if source_count and int(health["personas"] or 0) == 0:
                raise RuntimeError(
                    "Gate marketing NO aprobado: clientes existen pero el mart quedó vacío"
                )

            cur.execute(
                """
                INSERT INTO analytics.marketing_audiencias_refresh_runs (
                    started_at, finished_at, inactivity_days, personas, positivas,
                    negativas_sin_avance, exclusiones, contacto_valido, aptas_entrega_externa,
                    con_proyecto_origen, con_proyecto_conversion, cambios_proyecto,
                    project_links
                ) VALUES (
                    transaction_timestamp(), clock_timestamp(), %(days)s, %(personas)s,
                    %(positivas)s, %(negativas)s, %(exclusiones)s, %(contacto)s, %(aptas)s,
                    %(origen)s, %(conversion)s, %(cambios)s, %(links)s
                )
                """,
                {
                    "days": inactivity_days,
                    "personas": int(health["personas"] or 0),
                    "positivas": int(health["positivas"] or 0),
                    "negativas": int(health["negativas_sin_avance"] or 0),
                    "exclusiones": int(health["exclusiones"] or 0),
                    "contacto": int(health["contacto_valido"] or 0),
                    "aptas": int(health["aptas_entrega_externa"] or 0),
                    "origen": int(health["con_proyecto_origen"] or 0),
                    "conversion": int(health["con_proyecto_conversion"] or 0),
                    "cambios": int(health["cambios_proyecto"] or 0),
                    "links": int(health["project_links"] or 0),
                },
            )

    return {
        key: int(value or 0)
        for key, value in health.items()
        if key != "actualizado_en"
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresca audiencias LAL/RMKT usando solo PostgreSQL local, "
            "con linaje de proyecto origen -> proforma -> conversión."
        )
    )
    parser.add_argument(
        "--inactivity-days",
        type=int,
        default=int(os.getenv("MARKETING_INACTIVITY_DAYS", "180")),
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    try:
        validate_inactivity_days(args.inactivity_days)
    except ValueError as exc:
        parser.error(str(exc))

    with connect_postgres(load_settings(require_source=False)) as conn:
        health = refresh(
            conn,
            inactivity_days=args.inactivity_days,
            timeout_seconds=args.timeout_seconds,
        )

    print("[MARKETING_AUDIENCES] " + " | ".join(f"{k}={v}" for k, v in health.items()))
    print("Gate marketing_audiencias APROBADO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
