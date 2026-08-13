DO $$
DECLARE
    missing text[];
BEGIN
    SELECT array_agg(req)
    INTO missing
    FROM (
        VALUES
          ('raw_cygnus.procesos'),
          ('raw_cygnus.proforma_unidad'),
          ('raw_cygnus.datos_extras')
    ) v(req)
    WHERE to_regclass(req) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan tablas requeridas: %', missing;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM raw_cygnus.procesos
        GROUP BY nombre,id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'raw_cygnus.procesos no es único por (nombre,id)';
    END IF;
END $$;

-- Validar columnas físicamente demostradas/requeridas.
WITH required(table_name, column_name) AS (
    VALUES
      ('procesos','id'),
      ('procesos','nombre'),
      ('procesos','estado'),
      ('procesos','nombre_flujo'),
      ('procesos','fecha_inicio'),
      ('procesos','fecha_actualizacion'),
      ('procesos','codigo_proforma'),
      ('procesos','codigo_unidad'),
      ('procesos','codigo_proyecto'),
      ('procesos','documento_cliente'),
      ('procesos','usuario_separacion'),
      ('procesos','tipo_unidad_principal'),
      ('proforma_unidad','id'),
      ('proforma_unidad','codigo_proforma'),
      ('proforma_unidad','codigo_unidad'),
      ('proforma_unidad','codigo_proyecto'),
      ('proforma_unidad','fecha_creacion'),
      ('datos_extras','id'),
      ('datos_extras','codigo'),
      ('datos_extras','entidad'),
      ('datos_extras','nombre'),
      ('datos_extras','valor'),
      ('datos_extras','fecha_actualizacion')
)
SELECT r.*
FROM required r
LEFT JOIN information_schema.columns c
  ON c.table_schema='raw_cygnus'
 AND c.table_name=r.table_name
 AND c.column_name=r.column_name
WHERE c.column_name IS NULL;

-- El resultado anterior DEBE tener 0 filas.


DO $$
DECLARE
    missing_count integer;
    multi_cycle_count integer;
BEGIN
    WITH required(table_name, column_name) AS (
        VALUES
          ('procesos','id'),
          ('procesos','nombre'),
          ('procesos','estado'),
          ('procesos','nombre_flujo'),
          ('procesos','fecha_inicio'),
          ('procesos','fecha_actualizacion'),
          ('procesos','codigo_proforma'),
          ('procesos','codigo_unidad'),
          ('procesos','codigo_proyecto'),
          ('procesos','documento_cliente'),
          ('procesos','usuario_separacion'),
          ('procesos','tipo_unidad_principal'),
          ('proforma_unidad','id'),
          ('proforma_unidad','codigo_proforma'),
          ('proforma_unidad','codigo_unidad'),
          ('proforma_unidad','codigo_proyecto'),
          ('proforma_unidad','fecha_creacion'),
          ('proforma_unidad','fecha_actualizacion'),
          ('datos_extras','id'),
          ('datos_extras','codigo'),
          ('datos_extras','entidad'),
          ('datos_extras','nombre'),
          ('datos_extras','valor'),
          ('datos_extras','fecha_actualizacion')
    )
    SELECT count(*)
      INTO missing_count
    FROM required r
    LEFT JOIN information_schema.columns c
      ON c.table_schema='raw_cygnus'
     AND c.table_name=r.table_name
     AND c.column_name=r.column_name
    WHERE c.column_name IS NULL;

    IF missing_count > 0 THEN
        RAISE EXCEPTION
            'Fase B detenida: faltan % columnas requeridas. Ejecuta el SELECT anterior para identificarlas.',
            missing_count;
    END IF;

    SELECT count(*)
      INTO multi_cycle_count
    FROM (
        SELECT codigo_proforma,codigo_unidad
        FROM raw_cygnus.procesos
        WHERE nombre='Separacion'
          AND fecha_inicio IS NOT NULL
          AND coalesce(nombre_flujo,'') <> 'Desistimiento de visita'
        GROUP BY codigo_proforma,codigo_unidad
        HAVING count(*) > 1
    ) x;

    IF multi_cycle_count > 0 THEN
        RAISE EXCEPTION
            'OPEN BUSINESS RULE: existen % proforma-unidad con múltiples Separaciones. Implementar cycle_sequence antes del backfill.',
            multi_cycle_count;
    END IF;
END $$;
