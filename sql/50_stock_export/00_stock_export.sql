-- Stock disponible exportable a Excel desde Medallio DW.
-- Fuente canónica: core.v_unidades_fuentes.
-- Regla comercial inicial (post feria): Fénix, Urbanzen y Tizón = 10%.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.stock_discount_rules (
    project_key         text PRIMARY KEY,
    project_display_name text NOT NULL,
    discount_pct        numeric(8,6) NOT NULL CHECK (discount_pct >= 0 AND discount_pct < 1),
    valid_from          date NOT NULL DEFAULT CURRENT_DATE,
    valid_to            date,
    active              boolean NOT NULL DEFAULT true,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

INSERT INTO analytics.stock_discount_rules (
    project_key, project_display_name, discount_pct, valid_from, valid_to, active
)
VALUES
    ('FENIX',    'Fénix',          0.10, CURRENT_DATE, NULL, true),
    ('URBANZEN', 'Urbanzen',       0.10, CURRENT_DATE, NULL, true),
    ('TIZON',    'Tizón y Bueno',  0.10, CURRENT_DATE, NULL, true)
ON CONFLICT (project_key) DO UPDATE
SET project_display_name = EXCLUDED.project_display_name,
    discount_pct = EXCLUDED.discount_pct,
    active = EXCLUDED.active,
    updated_at = now();

CREATE OR REPLACE VIEW analytics.v_stock_disponible_export AS
WITH unidades AS (
    SELECT
        u.*,
        translate(upper(coalesce(u.nombre_proyecto, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS proyecto_norm,
        translate(upper(coalesce(u.estado_comercial, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS estado_norm,
        translate(upper(coalesce(u.tipo_unidad, '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') AS tipo_norm,
        row_number() OVER (
            PARTITION BY coalesce(u.codigo_proyecto, u.nombre_proyecto), u.codigo
            ORDER BY u.source_loaded_at DESC NULLS LAST,
                     CASE WHEN u.esquema_fuente = 'raw_cygnus' THEN 0 ELSE 1 END
        ) AS rn
    FROM core.v_unidades_fuentes u
), reglas AS (
    SELECT *
    FROM analytics.stock_discount_rules
    WHERE active
      AND valid_from <= CURRENT_DATE
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
)
SELECT
    r.project_display_name AS proyecto,
    u.codigo_proyecto,
    u.codigo AS unidad,
    CASE
        WHEN u.tipo_norm LIKE '%ESTACION%' THEN 'Estacionamiento'
        WHEN u.tipo_norm LIKE '%DEPOSITO%' THEN 'Depósito'
        WHEN u.tipo_norm LIKE '%DEPART%' OR u.tipo_norm LIKE '%FLAT%' OR u.tipo_norm LIKE '%DUPLEX%' OR u.tipo_norm LIKE '%TRIPLEX%'
            THEN 'Departamento'
        ELSE initcap(lower(coalesce(u.tipo_unidad, 'Sin clasificar')))
    END AS tipo_unidad,
    u.nombre_tipologia,
    u.piso,
    u.area_total,
    u.estado_comercial,
    u.precio_lista,
    r.discount_pct,
    round(u.precio_lista * (1 - r.discount_pct), 2) AS precio_con_descuento,
    coalesce(u.moneda_precio_lista, 'PEN') AS moneda,
    greatest(u.fecha_precio_actualizado, u.fecha_actualizacion, u.source_loaded_at::date) AS fecha_actualizacion_dato,
    u.esquema_fuente,
    u.unidad_fuente_key
FROM unidades u
JOIN reglas r
  ON position(r.project_key in u.proyecto_norm) > 0
WHERE u.rn = 1
  AND u.estado_norm = 'DISPONIBLE';

COMMENT ON VIEW analytics.v_stock_disponible_export IS
'Stock disponible vigente por unidad para exportación ejecutiva. Precio con descuento usa analytics.stock_discount_rules.';
