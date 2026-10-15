"""Build LAL/RMKT audience marts from the local Medallio replica only."""

from __future__ import annotations

import argparse
import os

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


REQUIRED_RELATIONS = (
    "raw_cygnus.clientes",
    "raw_cygnus.procesos",
    "raw_cygnus.proformas",
    "staging.clientes_calidad",
    "analytics.marketing_audiencias",
)


def validate_inactivity_days(value: int) -> int:
    if not 1 <= value <= 3650:
        raise ValueError("inactivity_days debe estar entre 1 y 3650")
    return value


REFRESH_SQL = r"""
DROP TABLE IF EXISTS pg_temp.marketing_audiencias_next;
CREATE TEMP TABLE marketing_audiencias_next ON COMMIT DROP AS
WITH clientes AS (
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
        END AS fecha_cliente
    FROM staging.clientes_calidad c
    LEFT JOIN raw_cygnus.clientes r
      ON r.id::text = c.source_id
),
cliente_keys AS (
    SELECT persona_key, 'source_id'::text AS key_type, source_id AS key_value
    FROM clientes WHERE NULLIF(source_id, '') IS NOT NULL
    UNION ALL
    SELECT persona_key, 'documento', dq_documento_limpio
    FROM clientes WHERE NULLIF(dq_documento_limpio, '') IS NOT NULL
),
procesos_base AS (
    SELECT
        to_jsonb(p) AS row_data,
        NULLIF(regexp_replace(p.documento_cliente::text, '[^0-9]', '', 'g'), '') AS documento,
        COALESCE(
            NULLIF(to_jsonb(p) ->> 'cliente_id', ''),
            NULLIF(to_jsonb(p) ->> 'id_cliente', ''),
            NULLIF(to_jsonb(p) ->> 'codigo_cliente', '')
        ) AS source_id,
        p.fecha_inicio::timestamptz AS fecha_evento,
        translate(lower(btrim(p.nombre::text)), 'áéíóúñ', 'aeioun') AS nombre_evento,
        NULLIF(btrim(p.codigo_proforma::text), '') AS codigo_proforma
    FROM raw_cygnus.procesos p
),
proformas_base AS (
    SELECT
        to_jsonb(p) AS row_data,
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
        END AS fecha_evento
    FROM raw_cygnus.proformas p
),
eventos AS (
    SELECT
        documento,
        source_id,
        CASE
            WHEN nombre_evento IN ('venta', 'minuta') THEN 3
            WHEN nombre_evento = 'separacion' THEN 2
            WHEN codigo_proforma IS NOT NULL THEN 1
            ELSE 0
        END AS nivel,
        fecha_evento
    FROM procesos_base
    WHERE nombre_evento IN ('venta', 'minuta', 'separacion')
       OR codigo_proforma IS NOT NULL
    UNION ALL
    SELECT documento, source_id, 1, fecha_evento
    FROM proformas_base
),
evento_keys AS (
    SELECT 'source_id'::text AS key_type, source_id AS key_value, nivel, fecha_evento
    FROM eventos WHERE NULLIF(source_id, '') IS NOT NULL
    UNION ALL
    SELECT 'documento', documento, nivel, fecha_evento
    FROM eventos WHERE NULLIF(documento, '') IS NOT NULL
),
avances AS (
    SELECT
        ck.persona_key,
        max(ek.nivel) AS nivel,
        min(ek.fecha_evento) FILTER (WHERE ek.nivel = 1) AS fecha_proforma,
        min(ek.fecha_evento) FILTER (WHERE ek.nivel = 2) AS fecha_separacion,
        min(ek.fecha_evento) FILTER (WHERE ek.nivel = 3) AS fecha_minuta_venta,
        max(ek.fecha_evento) AS fecha_ultimo_avance
    FROM cliente_keys ck
    JOIN evento_keys ek
      ON ek.key_type = ck.key_type
     AND ek.key_value = ck.key_value
    GROUP BY ck.persona_key
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
    r.dq_medio_captacion AS medio_captacion,
    r.dq_proyecto AS proyecto,
    r.fecha_cliente,
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
    (r.nivel = 0 AND COALESCE(r.fecha_cliente <= current_date - %(inactivity_days)s, false))
        AS negativa_sin_avance,
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
LEFT JOIN analytics.marketing_consentimientos c USING (persona_key)
LEFT JOIN analytics.marketing_supresiones s USING (persona_key)
WHERE r.rn = 1;

DELETE FROM analytics.marketing_audiencias;
INSERT INTO analytics.marketing_audiencias (
    persona_key, source_id, nombres, apellidos, celular, email,
    medio_captacion, proyecto, fecha_cliente, fecha_proforma,
    fecha_separacion, fecha_minuta_venta, fecha_ultimo_avance, etapa_maxima,
    positiva, negativa_sin_avance, exclusion_convertido,
    exclusion_contacto_invalido, exclusion_no_contactar, contacto_valido,
    consentimiento_publicidad_verificado, apto_entrega_externa, actualizado_en
)
SELECT
    persona_key, source_id, nombres, apellidos, celular, email,
    medio_captacion, proyecto, fecha_cliente, fecha_proforma,
    fecha_separacion, fecha_minuta_venta, fecha_ultimo_avance, etapa_maxima,
    positiva, negativa_sin_avance, exclusion_convertido,
    exclusion_contacto_invalido, exclusion_no_contactar, contacto_valido,
    consentimiento_publicidad_verificado, apto_entrega_externa, actualizado_en
FROM marketing_audiencias_next;
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
            cur.execute("LOCK TABLE analytics.marketing_audiencias IN SHARE ROW EXCLUSIVE MODE")
            cur.execute(REFRESH_SQL, {"inactivity_days": inactivity_days})
            cur.execute("SELECT * FROM analytics.v_marketing_audiencias_health")
            columns = [item.name for item in cur.description]
            health = dict(zip(columns, cur.fetchone()))
            cur.execute("SELECT count(*) FROM staging.clientes_calidad")
            source_count = int(cur.fetchone()[0] or 0)
            if source_count and int(health["personas"] or 0) == 0:
                raise RuntimeError("Gate marketing NO aprobado: clientes existen pero el mart quedó vacío")
            cur.execute(
                """
                INSERT INTO analytics.marketing_audiencias_refresh_runs (
                    started_at, finished_at, inactivity_days, personas, positivas,
                    negativas_sin_avance, exclusiones, contacto_valido, aptas_entrega_externa
                ) VALUES (
                    transaction_timestamp(), clock_timestamp(), %(days)s, %(personas)s,
                    %(positivas)s, %(negativas)s, %(exclusiones)s,
                    %(contacto)s, %(aptas)s
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
                },
            )
    return {key: int(value or 0) for key, value in health.items() if key != "actualizado_en"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresca audiencias LAL/RMKT usando solo PostgreSQL local."
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
