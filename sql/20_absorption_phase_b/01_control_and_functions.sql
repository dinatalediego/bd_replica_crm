CREATE TABLE IF NOT EXISTS etl_control.business_exclusions (
    exclusion_id bigserial PRIMARY KEY,
    entity_type text NOT NULL,
    entity_key text NOT NULL,
    scope text NOT NULL,
    reason text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    valid_from date,
    valid_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL DEFAULT current_user,
    notes text
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_business_exclusions_active
ON etl_control.business_exclusions(entity_type, entity_key, scope)
WHERE is_active;

-- Exclusión conocida, administrable y no hardcodeada en transforms.
INSERT INTO etl_control.business_exclusions(
    entity_type, entity_key, scope, reason, is_active, notes
)
SELECT
    'PROFORMA',
    '2026-0002275',
    'COMMERCIAL_ANALYTICS',
    'Registro erróneo de origen',
    true,
    'Migrado desde regla histórica es_valido'
WHERE NOT EXISTS (
    SELECT 1
    FROM etl_control.business_exclusions
    WHERE entity_type='PROFORMA'
      AND entity_key='2026-0002275'
      AND scope='COMMERCIAL_ANALYTICS'
      AND is_active
);

CREATE OR REPLACE FUNCTION analytics.try_parse_business_date(p_value text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $$
DECLARE
    s text := btrim(p_value);
    d date;
    fmt text;
BEGIN
    IF p_value IS NULL OR s = '' THEN
        RETURN NULL;
    END IF;

    IF s ~ '^\d{4}-\d{2}-\d{2}$' THEN
        fmt := 'YYYY-MM-DD';
    ELSIF s ~ '^\d{2}-\d{2}-\d{4}$' THEN
        fmt := 'DD-MM-YYYY';
    ELSE
        RETURN NULL;
    END IF;

    BEGIN
        d := to_date(s, fmt);
        IF to_char(d, fmt) <> s THEN
            RETURN NULL;
        END IF;
        RETURN d;
    EXCEPTION WHEN others THEN
        RETURN NULL;
    END;
END;
$$;

-- Parser monetario conservador.
-- Devuelve NULL si el formato no es reconocible con seguridad.
CREATE OR REPLACE FUNCTION analytics.try_parse_numeric(p_value text)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    s text;
    result numeric;
BEGIN
    IF p_value IS NULL OR btrim(p_value) = '' THEN
        RETURN NULL;
    END IF;

    s := regexp_replace(btrim(p_value), '[^0-9,.\-]', '', 'g');

    BEGIN
        -- Ambos separadores: el último se interpreta como decimal.
        IF s ~ ',' AND s ~ '\.' THEN
            IF strpos(reverse(s), ',') < strpos(reverse(s), '.') THEN
                -- coma aparece más cerca del final => decimal coma
                s := replace(s, '.', '');
                s := replace(s, ',', '.');
            ELSE
                -- punto aparece más cerca del final => decimal punto
                s := replace(s, ',', '');
            END IF;
        ELSIF s ~ ',' THEN
            -- Una coma con 1-2 decimales: decimal. En otro caso, miles.
            IF s ~ ',[0-9]{1,2}$' THEN
                s := replace(s, ',', '.');
            ELSE
                s := replace(s, ',', '');
            END IF;
        END IF;

        result := s::numeric;
        RETURN result;
    EXCEPTION WHEN others THEN
        RETURN NULL;
    END;
END;
$$;

CREATE TABLE IF NOT EXISTS observability.absorption_quality_results (
    quality_result_id bigserial PRIMARY KEY,
    checked_at timestamptz NOT NULL DEFAULT now(),
    check_name text NOT NULL,
    severity text NOT NULL,
    failed_rows bigint NOT NULL,
    status text NOT NULL,
    details jsonb
);
