-- Project-purpose governance for stock and absorption.
--
-- Some CRM projects are acquisition containers and are not physical inventory.
-- They remain in CORE for lead attribution, but must not enter stock or absorption.
-- Business rule v1.1: project_id=24, nombre='Campañas', is lead-capture only.

CREATE TABLE IF NOT EXISTS analytics.dim_proyecto_semantica (
    proyecto_id integer PRIMARY KEY,
    codigo_proyecto text NOT NULL UNIQUE,
    nombre_proyecto text,
    proposito_proyecto text NOT NULL,
    flag_gestion_stock boolean NOT NULL,
    flag_absorcion boolean NOT NULL,
    motivo_exclusion_stock text,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE PROCEDURE analytics.refresh_project_scope_v11()
LANGUAGE plpgsql
AS $$
BEGIN
    TRUNCATE TABLE analytics.dim_proyecto_semantica;

    INSERT INTO analytics.dim_proyecto_semantica(
        proyecto_id,codigo_proyecto,nombre_proyecto,
        proposito_proyecto,flag_gestion_stock,flag_absorcion,
        motivo_exclusion_stock
    )
    SELECT
        p.proyecto_id,
        p.codigo_proyecto,
        p.nombre_proyecto,
        CASE
            WHEN p.proyecto_id=24 THEN 'CAPTACION_LEADS'
            ELSE 'INVENTARIO_COMERCIAL'
        END,
        (p.proyecto_id<>24),
        (p.proyecto_id<>24),
        CASE
            WHEN p.proyecto_id=24
                THEN 'Proyecto Campañas: contenedor CRM para captación de leads; no representa stock físico.'
        END
    FROM core.dim_proyecto p;

    -- Defensive cleanup: even if a lead-only project ever receives CRM process
    -- events, those rows must not survive in stock/absorption facts.
    DELETE FROM analytics.fact_absorcion_proyecto_tipo_diario a
    USING analytics.dim_proyecto_semantica p
    WHERE a.codigo_proyecto=p.codigo_proyecto
      AND NOT p.flag_absorcion;

    DELETE FROM analytics.fact_stock_ofertado_diario_tipo s
    USING analytics.dim_proyecto_semantica p
    WHERE s.codigo_proyecto=p.codigo_proyecto
      AND NOT p.flag_gestion_stock;
END $$;

CREATE OR REPLACE VIEW analytics.v_unidades_stock_elegibles AS
SELECT
    u.*,
    p.proyecto_id,
    p.nombre_proyecto,
    p.proposito_proyecto,
    p.flag_gestion_stock,
    p.flag_absorcion
FROM analytics.dim_unidad_semantica u
JOIN analytics.dim_proyecto_semantica p
  ON p.codigo_proyecto=u.codigo_proyecto
WHERE p.flag_gestion_stock;

-- Override the current snapshot capture so lead-only CRM containers are not
-- misrepresented as physical stock. The unit remains visible in CORE and in
-- dim_unidad_semantica for audit, but is excluded from stock facts.
CREATE OR REPLACE PROCEDURE analytics.refresh_stock_snapshot_actual_v11()
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM analytics.fact_stock_snapshot_diario_unidad
    WHERE fecha_snapshot=current_date;

    INSERT INTO analytics.fact_stock_snapshot_diario_unidad(
        fecha_snapshot,codigo_unidad,codigo_proyecto,tipo_unidad_consolidado,
        estado_comercial_consolidado,orden_estado,
        flag_departamento,flag_estacionamiento,flag_deposito,flag_local,flag_otro_tipo,
        flag_disponible,flag_bloqueado,flag_estado_separado,flag_vendido,flag_otro_estado
    )
    SELECT
        current_date,
        u.codigo_unidad,
        u.codigo_proyecto,
        u.tipo_unidad_consolidado,
        u.estado_comercial_consolidado,
        u.orden_estado,
        u.flag_departamento,
        u.flag_estacionamiento,
        u.flag_deposito,
        u.flag_local,
        u.flag_otro_tipo,
        u.flag_disponible,
        u.flag_bloqueado,
        u.flag_estado_separado,
        u.flag_vendido,
        u.flag_otro_estado
    FROM analytics.dim_unidad_semantica u
    JOIN analytics.dim_proyecto_semantica p
      ON p.codigo_proyecto=u.codigo_proyecto
    WHERE p.flag_gestion_stock;
END $$;

CREATE OR REPLACE VIEW analytics.v_proyectos_fuera_stock AS
SELECT *
FROM analytics.dim_proyecto_semantica
WHERE NOT flag_gestion_stock;
