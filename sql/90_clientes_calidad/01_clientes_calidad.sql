CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE FUNCTION staging.dq_normalize_text(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NULLIF(regexp_replace(btrim(value), '[[:space:]]+', ' ', 'g'), '')
$$;

CREATE TABLE IF NOT EXISTS staging.clientes_calidad (
    source_id                           text,
    source_row_hash                     text NOT NULL,
    nombres                             text,
    apellidos                           text,
    nombre                              text,
    documento                           text,
    numero_documento                    text,
    celulares                           text,
    celular                             text,
    telefono                            text,
    email                               text,
    correo                              text,
    nombre_proyecto                     text,
    proyecto                            text,
    vendedor                            text,
    asesor                              text,
    usuario_asignado                    text,
    medio_captacion                     text,
    canal                               text,
    fuente                              text,
    estado                              text,
    estado_cliente                      text,
    dq_nombre_cliente                   text,
    dq_documento_limpio                 text,
    dq_celular_limpio                   text,
    dq_estado_celular                   text,
    dq_fuente_celular                   text,
    dq_email_limpio                     text,
    dq_asesor_comercial                 text,
    dq_proyecto                         text,
    dq_medio_captacion                  text,
    dq_estado_cliente                   text,
    dq_nombre_completo_ok               boolean NOT NULL,
    dq_documento_ok                     boolean NOT NULL,
    dq_celular_ok                       boolean NOT NULL,
    dq_email_ok                         boolean NOT NULL,
    dq_contacto_valido_ok               boolean NOT NULL,
    dq_proyecto_ok                      boolean NOT NULL,
    dq_asesor_ok                        boolean NOT NULL,
    dq_medio_captacion_ok               boolean NOT NULL,
    dq_estado_cliente_ok                boolean NOT NULL,
    dq_cliente_sin_identidad            boolean NOT NULL,
    dq_cliente_sin_contacto             boolean NOT NULL,
    dq_score_cliente                    integer NOT NULL,
    dq_nivel_cliente                    text NOT NULL,
    dq_nombre_completo_ok_estado        text NOT NULL,
    dq_documento_ok_estado              text NOT NULL,
    dq_celular_ok_estado                text NOT NULL,
    dq_email_ok_estado                  text NOT NULL,
    dq_contacto_valido_ok_estado        text NOT NULL,
    dq_proyecto_ok_estado               text NOT NULL,
    dq_asesor_ok_estado                 text NOT NULL,
    dq_medio_captacion_ok_estado        text NOT NULL,
    dq_estado_cliente_ok_estado         text NOT NULL,
    dq_cliente_sin_identidad_estado     text NOT NULL,
    dq_cliente_sin_contacto_estado      text NOT NULL,
    refreshed_at                        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clientes_calidad_source_id
    ON staging.clientes_calidad (source_id);
CREATE INDEX IF NOT EXISTS idx_clientes_calidad_documento
    ON staging.clientes_calidad (dq_documento_limpio);
CREATE INDEX IF NOT EXISTS idx_clientes_calidad_celular
    ON staging.clientes_calidad (dq_celular_limpio);

-- Aggregate operational evidence only; no customer PII in this table.
CREATE TABLE IF NOT EXISTS staging.clientes_calidad_refresh_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    rule_hash text NOT NULL,
    mode text NOT NULL,
    source_rows bigint NOT NULL,
    inserted_rows bigint NOT NULL,
    updated_rows bigint NOT NULL,
    deleted_rows bigint NOT NULL,
    unchanged_rows bigint NOT NULL
);

CREATE OR REPLACE PROCEDURE staging.refresh_clientes_calidad()
LANGUAGE plpgsql
AS $$
DECLARE
    v_started timestamptz := clock_timestamp();
    v_rule_hash text;
    v_rebuild boolean;
    v_inserted bigint;
    v_updated bigint;
    v_deleted bigint;
    v_source bigint;
    v_changed bigint;
BEGIN
    -- Fail rather than run two DQ writers at once; the DW must not report OK.
    IF NOT pg_try_advisory_xact_lock(9042026, 2) THEN
        RAISE EXCEPTION 'clientes_calidad: otro refresh sigue activo; reintentar al terminar.';
    END IF;
    IF to_regclass('raw_cygnus.clientes') IS NULL THEN
        RAISE EXCEPTION 'No existe raw_cygnus.clientes; ejecutar la sincronización RAW antes del refresh DQ.';
    END IF;

    -- Stabilize RAW until validation/commit, and serialize all target writers.
    -- Readers (Power BI) continue seeing the previous committed version.
    LOCK TABLE raw_cygnus.clientes IN SHARE MODE;
    LOCK TABLE staging.clientes_calidad IN SHARE ROW EXCLUSIVE MODE;

    DROP TABLE IF EXISTS pg_temp.clientes_dq_source;
    DROP TABLE IF EXISTS pg_temp.clientes_dq_changed;
    CREATE TEMP TABLE clientes_dq_source ON COMMIT DROP AS
    SELECT src ->> 'id' AS source_id, md5(src::text) AS source_row_hash, src
    FROM (
        SELECT to_jsonb(c) - '_etl_loaded_at' - '_etl_source_run_id' AS src
        FROM raw_cygnus.clientes AS c
    ) AS raw;

    IF EXISTS (SELECT 1 FROM clientes_dq_source
               WHERE source_id IS NULL OR btrim(source_id) = '') THEN
        RAISE EXCEPTION 'clientes_calidad: RAW contiene id nulo/vacio; no se modifica staging.';
    END IF;
    IF EXISTS (SELECT 1 FROM clientes_dq_source
               GROUP BY source_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'clientes_calidad: RAW contiene id duplicado; no se modifica staging.';
    END IF;
    CREATE UNIQUE INDEX ON clientes_dq_source (source_id);
    ANALYZE clientes_dq_source;
    SELECT count(*) INTO v_source FROM clientes_dq_source;

    -- A new rule definition triggers exactly one rebuild, including legacy hashes.
    v_rule_hash := md5(
        pg_get_functiondef('staging.refresh_clientes_calidad()'::regprocedure)
        || pg_get_functiondef('staging.dq_normalize_text(text)'::regprocedure)
    );
    SELECT COALESCE((SELECT rule_hash IS DISTINCT FROM v_rule_hash
                     FROM staging.clientes_calidad_refresh_runs
                     ORDER BY run_id DESC LIMIT 1), true)
           OR COALESCE(current_setting('medallio.clientes_calidad_full', true) = 'on', false)
    INTO v_rebuild;

    CREATE TEMP TABLE clientes_dq_changed ON COMMIT DROP AS
    SELECT r.source_id
    FROM clientes_dq_source AS r
    LEFT JOIN (
        SELECT source_id, min(source_row_hash) AS source_row_hash, count(*) AS copies
        FROM staging.clientes_calidad GROUP BY source_id
    ) AS t USING (source_id)
    WHERE v_rebuild OR t.source_id IS NULL OR t.copies <> 1
          OR t.source_row_hash IS DISTINCT FROM r.source_row_hash;
    CREATE UNIQUE INDEX ON clientes_dq_changed (source_id);
    ANALYZE clientes_dq_changed;
    SELECT count(*) INTO v_changed FROM clientes_dq_changed;
    SELECT count(*) INTO v_inserted FROM clientes_dq_changed AS c
    WHERE NOT EXISTS (SELECT 1 FROM staging.clientes_calidad AS t
                      WHERE t.source_id = c.source_id);
    v_updated := v_changed - v_inserted;

    DELETE FROM staging.clientes_calidad AS t
    WHERE NOT EXISTS (SELECT 1 FROM clientes_dq_source AS r WHERE r.source_id = t.source_id);
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    -- Replace only changed identities, atomically. Unchanged timestamps stay intact.
    DELETE FROM staging.clientes_calidad AS t
    USING clientes_dq_changed AS c WHERE t.source_id = c.source_id;

    INSERT INTO staging.clientes_calidad (
        source_id,
        source_row_hash,
        nombres,
        apellidos,
        nombre,
        documento,
        numero_documento,
        celulares,
        celular,
        telefono,
        email,
        correo,
        nombre_proyecto,
        proyecto,
        vendedor,
        asesor,
        usuario_asignado,
        medio_captacion,
        canal,
        fuente,
        estado,
        estado_cliente,
        dq_nombre_cliente,
        dq_documento_limpio,
        dq_celular_limpio,
        dq_estado_celular,
        dq_fuente_celular,
        dq_email_limpio,
        dq_asesor_comercial,
        dq_proyecto,
        dq_medio_captacion,
        dq_estado_cliente,
        dq_nombre_completo_ok,
        dq_documento_ok,
        dq_celular_ok,
        dq_email_ok,
        dq_contacto_valido_ok,
        dq_proyecto_ok,
        dq_asesor_ok,
        dq_medio_captacion_ok,
        dq_estado_cliente_ok,
        dq_cliente_sin_identidad,
        dq_cliente_sin_contacto,
        dq_score_cliente,
        dq_nivel_cliente,
        dq_nombre_completo_ok_estado,
        dq_documento_ok_estado,
        dq_celular_ok_estado,
        dq_email_ok_estado,
        dq_contacto_valido_ok_estado,
        dq_proyecto_ok_estado,
        dq_asesor_ok_estado,
        dq_medio_captacion_ok_estado,
        dq_estado_cliente_ok_estado,
        dq_cliente_sin_identidad_estado,
        dq_cliente_sin_contacto_estado,
        refreshed_at
    )
    WITH source_rows AS MATERIALIZED (
        SELECT r.src
        FROM clientes_dq_source AS r
        JOIN clientes_dq_changed AS c USING (source_id)
    ),
    extracted AS MATERIALIZED (
        SELECT
            src,
            src ->> 'id' AS source_id,
            md5(src::text) AS source_row_hash,
            staging.dq_normalize_text(src ->> 'nombres') AS nombres,
            staging.dq_normalize_text(src ->> 'apellidos') AS apellidos,
            staging.dq_normalize_text(src ->> 'nombre') AS nombre,
            staging.dq_normalize_text(src ->> 'documento') AS documento,
            staging.dq_normalize_text(src ->> 'numero_documento') AS numero_documento,
            CASE WHEN src ? 'celulares' THEN btrim(src ->> 'celulares') END AS celulares,
            CASE WHEN src ? 'celular' THEN btrim(src ->> 'celular') END AS celular,
            CASE WHEN src ? 'telefono' THEN btrim(src ->> 'telefono') END AS telefono,
            staging.dq_normalize_text(src ->> 'email') AS email,
            staging.dq_normalize_text(src ->> 'correo') AS correo,
            staging.dq_normalize_text(src ->> 'nombre_proyecto') AS nombre_proyecto,
            staging.dq_normalize_text(src ->> 'proyecto') AS proyecto,
            staging.dq_normalize_text(src ->> 'vendedor') AS vendedor,
            staging.dq_normalize_text(src ->> 'asesor') AS asesor,
            staging.dq_normalize_text(src ->> 'usuario_asignado') AS usuario_asignado,
            staging.dq_normalize_text(src ->> 'medio_captacion') AS medio_captacion,
            staging.dq_normalize_text(src ->> 'canal') AS canal,
            staging.dq_normalize_text(src ->> 'fuente') AS fuente,
            staging.dq_normalize_text(src ->> 'estado') AS estado,
            staging.dq_normalize_text(src ->> 'estado_cliente') AS estado_cliente,
            CASE
                WHEN src ? 'celulares' THEN src ->> 'celulares'
                WHEN src ? 'celular' THEN src ->> 'celular'
                ELSE NULL
            END AS valor_celular,
            CASE
                WHEN src ? 'celulares' THEN 'celulares'
                WHEN src ? 'celular' THEN 'celular'
                ELSE NULL
            END AS columna_celular
        FROM source_rows
    ),
    chosen AS MATERIALIZED (
        SELECT
            e.*,
            COALESCE(
                e.nombre,
                staging.dq_normalize_text(concat_ws(' ', e.nombres, e.apellidos))
            ) AS dq_nombre_cliente,
            NULLIF(
                regexp_replace(COALESCE(e.documento, e.numero_documento, ''), '[^0-9]', '', 'g'),
                ''
            ) AS dq_documento_limpio,
            CASE
                WHEN e.valor_celular IS NOT NULL THEN e.valor_celular
                ELSE e.telefono
            END AS telefono_elegido,
            CASE
                WHEN e.valor_celular IS NOT NULL THEN e.columna_celular
                WHEN e.telefono IS NOT NULL THEN 'telefono'
                ELSE NULL
            END AS dq_fuente_celular,
            lower(COALESCE(e.email, e.correo)) AS dq_email_limpio,
            COALESCE(e.vendedor, e.asesor, e.usuario_asignado) AS dq_asesor_comercial,
            COALESCE(e.nombre_proyecto, e.proyecto) AS dq_proyecto,
            COALESCE(e.medio_captacion, e.canal, e.fuente) AS dq_medio_captacion,
            COALESCE(e.estado, e.estado_cliente) AS dq_estado_cliente
        FROM extracted AS e
    ),
    phone_raw AS MATERIALIZED (
        SELECT
            c.*,
            regexp_replace(COALESCE(c.telefono_elegido, ''), '[^0-9]', '', 'g') AS digitos_raw,
            left(btrim(COALESCE(c.telefono_elegido, '')), 1) = '+' AS tiene_signo_mas
        FROM chosen AS c
    ),
    phone_int AS MATERIALIZED (
        SELECT
            p.*,
            p.digitos_raw LIKE '00%' AS tiene_prefijo00,
            CASE
                WHEN p.digitos_raw LIKE '00%' THEN substring(p.digitos_raw FROM 3)
                ELSE p.digitos_raw
            END AS digitos_internacionales
        FROM phone_raw AS p
    ),
    phone_country AS MATERIALIZED (
        SELECT
            p.*,
            length(p.digitos_internacionales) AS largo_internacional,
            p.digitos_internacionales LIKE '51%'
                AND (length(p.digitos_internacionales) - 2) IN (7, 8, 9) AS es_peru_con_codigo
        FROM phone_int AS p
    ),
    phone_local AS MATERIALIZED (
        SELECT
            p.*,
            CASE
                WHEN p.es_peru_con_codigo THEN substring(p.digitos_internacionales FROM 3)
                ELSE p.digitos_internacionales
            END AS numero_local_pe
        FROM phone_country AS p
    ),
    phone_flags AS MATERIALIZED (
        SELECT
            p.*,
            length(p.numero_local_pe) AS largo_local,
            length(p.numero_local_pe) = 9 AND p.numero_local_pe LIKE '9%' AS es_celular_peru,
            length(p.numero_local_pe) = 7 AS es_telefono_peru_local,
            p.es_peru_con_codigo AND length(p.numero_local_pe) = 8 AS es_telefono_peru_con_area,
            p.tiene_signo_mas OR p.tiene_prefijo00 AS es_formato_internacional_explicito
        FROM phone_local AS p
    ),
    phone_classified AS MATERIALIZED (
        SELECT
            p.*,
            (
                p.digitos_raw <> ''
                AND NOT p.es_peru_con_codigo
                AND NOT p.es_celular_peru
                AND NOT p.es_telefono_peru_local
                AND NOT p.es_telefono_peru_con_area
                AND p.largo_internacional BETWEEN 8 AND 15
                AND (
                    p.es_formato_internacional_explicito
                    OR (
                        NOT p.es_formato_internacional_explicito
                        AND p.largo_internacional BETWEEN 10 AND 15
                    )
                )
            ) AS es_celular_extranjero
        FROM phone_flags AS p
    ),
    dq_base AS MATERIALIZED (
        SELECT
            p.*,
            CASE
                WHEN p.digitos_raw = '' THEN NULL
                WHEN p.es_peru_con_codigo THEN p.numero_local_pe
                ELSE p.digitos_internacionales
            END AS dq_celular_limpio,
            CASE
                WHEN p.digitos_raw = '' THEN 'Vacío'
                WHEN p.es_celular_peru THEN 'Celular Perú válido'
                WHEN p.es_telefono_peru_con_area THEN 'Teléfono Perú con código de área válido'
                WHEN p.es_telefono_peru_local THEN 'Teléfono Perú válido'
                WHEN p.es_celular_extranjero THEN 'Celular extranjero'
                ELSE 'Revisar formato'
            END AS dq_estado_celular,
            (
                p.es_celular_peru
                OR p.es_telefono_peru_local
                OR p.es_telefono_peru_con_area
                OR p.es_celular_extranjero
            ) AS dq_celular_ok,
            (
                p.dq_nombre_cliente IS NOT NULL
                AND p.dq_nombre_cliente ~ '^[^[:space:]]+[[:space:]]+[^[:space:]]+'
            ) AS dq_nombre_completo_ok,
            (
                p.dq_documento_limpio IS NOT NULL
                AND length(p.dq_documento_limpio) BETWEEN 8 AND 12
            ) AS dq_documento_ok,
            (
                p.dq_email_limpio IS NOT NULL
                AND p.dq_email_limpio ~* '^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$'
            ) AS dq_email_ok,
            p.dq_proyecto IS NOT NULL AS dq_proyecto_ok,
            p.dq_asesor_comercial IS NOT NULL AS dq_asesor_ok,
            p.dq_medio_captacion IS NOT NULL AS dq_medio_captacion_ok,
            p.dq_estado_cliente IS NOT NULL AS dq_estado_cliente_ok
        FROM phone_classified AS p
    ),
    dq_flags AS MATERIALIZED (
        SELECT
            d.*,
            (d.dq_celular_ok OR d.dq_email_ok) AS dq_contacto_valido_ok,
            (NOT d.dq_nombre_completo_ok AND NOT d.dq_documento_ok) AS dq_cliente_sin_identidad,
            NOT (d.dq_celular_ok OR d.dq_email_ok) AS dq_cliente_sin_contacto
        FROM dq_base AS d
    ),
    scored AS MATERIALIZED (
        SELECT
            d.*,
            GREATEST(
                0,
                100
                - CASE WHEN d.dq_nombre_completo_ok THEN 0 ELSE 20 END
                - CASE WHEN d.dq_documento_ok THEN 0 ELSE 20 END
                - CASE WHEN d.dq_contacto_valido_ok THEN 0 ELSE 25 END
                - CASE WHEN d.dq_proyecto_ok THEN 0 ELSE 10 END
                - CASE WHEN d.dq_asesor_ok THEN 0 ELSE 15 END
                - CASE WHEN d.dq_medio_captacion_ok THEN 0 ELSE 5 END
                - CASE WHEN d.dq_estado_cliente_ok THEN 0 ELSE 5 END
            )::integer AS dq_score_cliente
        FROM dq_flags AS d
    )
    SELECT
        s.source_id,
        s.source_row_hash,
        s.nombres,
        s.apellidos,
        s.nombre,
        s.documento,
        s.numero_documento,
        s.celulares,
        s.celular,
        s.telefono,
        s.email,
        s.correo,
        s.nombre_proyecto,
        s.proyecto,
        s.vendedor,
        s.asesor,
        s.usuario_asignado,
        s.medio_captacion,
        s.canal,
        s.fuente,
        s.estado,
        s.estado_cliente,
        s.dq_nombre_cliente,
        s.dq_documento_limpio,
        s.dq_celular_limpio,
        s.dq_estado_celular,
        s.dq_fuente_celular,
        s.dq_email_limpio,
        s.dq_asesor_comercial,
        s.dq_proyecto,
        s.dq_medio_captacion,
        s.dq_estado_cliente,
        s.dq_nombre_completo_ok,
        s.dq_documento_ok,
        s.dq_celular_ok,
        s.dq_email_ok,
        s.dq_contacto_valido_ok,
        s.dq_proyecto_ok,
        s.dq_asesor_ok,
        s.dq_medio_captacion_ok,
        s.dq_estado_cliente_ok,
        s.dq_cliente_sin_identidad,
        s.dq_cliente_sin_contacto,
        s.dq_score_cliente,
        CASE
            WHEN s.dq_score_cliente >= 90 THEN '🟢 Óptimo'
            WHEN s.dq_score_cliente >= 75 THEN '🟡 Revisar'
            WHEN s.dq_score_cliente >= 60 THEN '🟠 Riesgoso'
            ELSE '🔴 Crítico'
        END AS dq_nivel_cliente,
        CASE WHEN s.dq_nombre_completo_ok THEN 'OK' ELSE 'error' END,
        CASE
            WHEN s.dq_documento_limpio IS NULL THEN 'revisar dni'
            WHEN s.dq_documento_ok THEN 'OK'
            ELSE 'error'
        END,
        CASE WHEN s.dq_celular_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_email_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_contacto_valido_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_proyecto_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_asesor_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_medio_captacion_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_estado_cliente_ok THEN 'OK' ELSE 'error' END,
        CASE WHEN s.dq_cliente_sin_identidad THEN 'error' ELSE 'OK' END,
        CASE WHEN s.dq_cliente_sin_contacto THEN 'error' ELSE 'OK' END,
        now()
    FROM scored AS s;

    -- Verify identities AND hashes, not only coincidentally equal row counts.
    IF (SELECT count(*) FROM staging.clientes_calidad) <> v_source
       OR EXISTS (
           SELECT 1 FROM clientes_dq_source AS r
           LEFT JOIN staging.clientes_calidad AS t USING (source_id)
           WHERE t.source_id IS NULL OR t.source_row_hash IS DISTINCT FROM r.source_row_hash
       ) THEN
        RAISE EXCEPTION 'clientes_calidad: gate de identidad/hash no aprobado; rollback.';
    END IF;
    INSERT INTO staging.clientes_calidad_refresh_runs (
        started_at, finished_at, rule_hash, mode, source_rows,
        inserted_rows, updated_rows, deleted_rows, unchanged_rows
    ) VALUES (
        v_started, clock_timestamp(), v_rule_hash,
        CASE WHEN v_rebuild THEN 'rebuild' ELSE 'incremental' END,
        v_source, v_inserted, v_updated, v_deleted, v_source - v_changed
    );
    IF v_changed > 0 OR v_deleted > 0 THEN
        ANALYZE staging.clientes_calidad;
    END IF;
END;
$$;

CREATE OR REPLACE VIEW staging.v_clientes_calidad_health AS
SELECT
    (SELECT COUNT(*) FROM raw_cygnus.clientes) AS filas_raw,
    COUNT(*) AS filas_staging,
    COUNT(*) FILTER (WHERE source_id IS NULL) AS source_id_nulo,
    COUNT(*) FILTER (WHERE dq_fuente_celular = 'celulares') AS celulares_usados,
    COUNT(*) FILTER (WHERE dq_fuente_celular = 'celular') AS celular_compatibilidad_usado,
    COUNT(*) FILTER (WHERE dq_fuente_celular = 'telefono') AS telefono_fallback_usado,
    COUNT(*) FILTER (WHERE dq_estado_celular = 'Celular extranjero') AS celulares_extranjeros,
    COUNT(*) FILTER (WHERE dq_estado_celular = 'Revisar formato') AS celulares_revisar_formato,
    COUNT(*) FILTER (WHERE dq_documento_ok_estado = 'revisar dni') AS documentos_revisar_dni,
    COUNT(*) FILTER (WHERE dq_cliente_sin_contacto) AS clientes_sin_contacto,
    MIN(refreshed_at) AS refreshed_at_min,
    MAX(refreshed_at) AS refreshed_at_max
FROM staging.clientes_calidad;

COMMENT ON TABLE staging.clientes_calidad IS
'Contrato de calidad de clientes derivado de raw_cygnus.clientes. Replica funcionalmente la lógica Power Query M sin exigir paridad textual.';
COMMENT ON COLUMN staging.clientes_calidad.dq_fuente_celular IS
'Prioridad funcional del M: celulares; celular solo si la columna plural no existe; telefono solo cuando el valor celular elegido es NULL.';
COMMENT ON COLUMN staging.clientes_calidad.dq_documento_ok_estado IS
'Usa revisar dni cuando el documento limpio es NULL; OK si pasa la validación aproximada y error en caso contrario.';
