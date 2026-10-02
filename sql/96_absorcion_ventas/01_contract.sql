-- Stock pendiente de venta reconstruido bajo el supuesto de alta por proyecto.
-- Regla retrospectiva aprobada 2026-10-02; no modifica Phase B ni su ledger.
CREATE TABLE IF NOT EXISTS analytics.absorcion_inicio_proyecto (
    codigo_proyecto text PRIMARY KEY,
    nombre_proyecto text NOT NULL,
    fecha_inicio_fuente date NOT NULL,
    fecha_ingreso_stock date NOT NULL,
    fuente text NOT NULL DEFAULT 'inicio por proyecto.csv / 2026-10-02',
    CHECK (fecha_ingreso_stock = date_trunc('month', fecha_inicio_fuente)::date)
);
INSERT INTO analytics.absorcion_inicio_proyecto
    (codigo_proyecto,nombre_proyecto,fecha_inicio_fuente,fecha_ingreso_stock)
SELECT codigo,nombre,fecha::date,date_trunc('month',fecha::date)::date
FROM (VALUES
 ('CRUZ','Edificio Santa Cruz Infinite','2019-10-02'),
 ('CUBA','Edificio Cuba Connect','2019-10-02'),
 ('ES','Edificio Saenz','2019-10-03'),
 ('URT','Los Jardines de Urteaga','2019-10-03'),
 ('001','Edificio Valdizan','2021-09-21'),
 ('MA','Edificio Mariategui','2021-12-18'),
 ('TP00','Tradiciones Prime','2022-09-01'),
 ('UN','Edificio Unique','2023-05-18'),
 ('TZ','Tizón y Bueno','2023-05-18'),
 ('EEUU','Edificio Urbanzen','2023-09-20'),
 ('FX','Fenix','2024-03-14'),
 ('SL','Sialia','2024-03-16'),
 ('GY','Alicanto','2024-04-15'),
 ('MD','Modena','2025-03-08'),
 ('CP','Capadocia','2025-03-12'),
 ('MT','Matera','2025-06-30'),
 ('NP','Torre Nápoles','2025-08-07')
) AS seed(codigo,nombre,fecha)
ON CONFLICT (codigo_proyecto) DO NOTHING;

-- Evidencia local por ciclo: conserva exclusiones y población de Phase B.
-- No exigir transición de inventario ni desplazar la fecha documental.
CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_ciclos AS
WITH extras AS (
    SELECT DISTINCT ON (codigo) codigo::text AS codigo_proforma,id::bigint AS id,
           valor,analytics.try_parse_business_date(valor) AS fecha
    FROM raw_cygnus.datos_extras
    WHERE lower(entidad)='proforma' AND lower(nombre)='fecha_de_minuta'
    ORDER BY codigo,fecha_actualizacion DESC NULLS LAST,id DESC
), ventas AS (
    SELECT DISTINCT ON (codigo_proforma,codigo_unidad)
           codigo_proforma::text,codigo_unidad::text,id::bigint,fecha_inicio::date AS fecha
    FROM raw_cygnus.procesos
    WHERE nombre='Venta' AND estado='Activo' AND fecha_inicio IS NOT NULL
    ORDER BY codigo_proforma,codigo_unidad,fecha_inicio,id
), anulaciones AS (
    SELECT codigo_proforma::text,codigo_unidad::text,min(fecha_inicio::date) AS fecha
    FROM raw_cygnus.procesos
    WHERE nombre='Anulacion' AND coalesce(nombre_flujo,'') <> 'Desistimiento de visita'
      AND fecha_inicio::date <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
    GROUP BY codigo_proforma,codigo_unidad
), evidencia AS (
    SELECT c.*,u.codigo_proyecto AS proyecto_unidad,
           e.fecha AS pago_ci,e.id AS pago_id,
           (nullif(btrim(e.valor),'') IS NOT NULL AND e.fecha IS NULL) AS pago_invalido,
           v.fecha AS venta_proceso,v.id AS venta_id,a.fecha AS fecha_anulacion,
           coalesce(c.fecha_separacion_raw,c.fecha_separacion) AS separacion_original,
           -- Mantener también el veto de la separación analítica ya gobernada.
           (c.fecha_separacion < DATE '2026-01-01'
            AND coalesce(c.fecha_separacion_raw,c.fecha_separacion) < DATE '2026-01-01') AS permite_legacy
    FROM analytics.v_absorcion_ventas_reconciliado c
    JOIN core.dim_unidad u USING (codigo_unidad)
    JOIN analytics.absorcion_inicio_proyecto i ON i.codigo_proyecto=u.codigo_proyecto
    LEFT JOIN extras e USING (codigo_proforma)
    LEFT JOIN ventas v USING (codigo_proforma,codigo_unidad)
    LEFT JOIN anulaciones a USING (codigo_proforma,codigo_unidad)
    WHERE lower(trim(u.tipo_unidad)) IN
      ('departamento','departamento flat','departamento duplex','departamento dúplex','departamento triplex','departamento tríplex')
      AND NOT EXISTS (SELECT 1 FROM etl_control.business_exclusions x
          WHERE x.entity_type='PROFORMA' AND x.entity_key=c.codigo_proforma
            AND x.scope='COMMERCIAL_ANALYTICS' AND x.is_active)
), fechas AS (
    SELECT e.*,
           CASE WHEN NOT coalesce(pago_invalido,false)
                THEN coalesce(pago_ci,CASE WHEN permite_legacy THEN venta_proceso END) END AS fecha_evidencia,
           CASE WHEN pago_ci IS NOT NULL THEN 'FECHA_DE_MINUTA'
                WHEN permite_legacy AND venta_proceso IS NOT NULL AND NOT coalesce(pago_invalido,false)
                THEN 'LEGACY_FECHA_FIRMA_PRE_2026' ELSE 'NO_CONFIRMADA' END AS metodo
    FROM evidencia e
), clasificado AS (
    SELECT f.*,
        CASE WHEN codigo_proyecto IS DISTINCT FROM proyecto_unidad THEN 'PROYECTO_INCONSISTENTE'
             WHEN fecha_anulacion IS NOT NULL THEN 'ANULADA_RETROSPECTIVAMENTE'
             WHEN pago_invalido THEN 'FECHA_PAGO_CI_INVALIDA'
             WHEN pago_ci IS NULL AND NOT permite_legacy AND venta_proceso IS NOT NULL THEN 'LEGACY_2026_PROHIBIDO'
             WHEN fecha_evidencia IS NULL AND venta_source_id IS NOT NULL THEN 'VENTA_SIN_FECHA_CONFIRMADA'
             WHEN fecha_evidencia IS NULL THEN 'SIN_VENTA_FECHADA'
             ELSE 'ELEGIBLE' END AS calidad
    FROM fechas f
)
SELECT codigo_unidad,codigo_proforma,codigo_proyecto,
       fecha_separacion,pago_ci AS fecha_de_minuta,venta_proceso AS fecha_firma_legacy,
       CASE WHEN calidad='ELEGIBLE' THEN fecha_evidencia END AS fecha_venta_validada,
       metodo AS metodo_fecha_venta,resultado_canonico,reconciliation_status,
       separacion_source_id,venta_id AS venta_source_id,pago_id AS datos_extras_fecha_minuta_id,
       refreshed_at,calidad AS calidad_ciclo,
       separacion_original AS fecha_separacion_raw,fecha_evidencia AS fecha_venta_documental,
       fecha_anulacion,
       concat_ws('; ',
           CASE WHEN calidad='ANULADA_RETROSPECTIVAMENTE' THEN 'Proforma anulada: venta excluida de todos los meses' END,
           CASE WHEN fecha_evidencia < separacion_original THEN 'Fecha documental anterior a separación original: se conserva la fecha de venta' END,
           CASE WHEN fecha_evidencia >= separacion_original AND fecha_evidencia < fecha_separacion
                THEN 'Venta recuperada: separación analítica desplazada por stock legacy' END,
           CASE WHEN calidad='ELEGIBLE' AND reconciliation_status<>'RECONCILED'
                THEN 'Evidencia documental aceptada sin exigir transición del ledger' END,
           CASE WHEN calidad NOT IN ('ELEGIBLE','SIN_VENTA_FECHADA','ANULADA_RETROSPECTIVAMENTE') THEN calidad END
       ) AS observacion
FROM clasificado;

-- Conservar el adjunto; mostrar por separado el inicio efectivo y su evidencia.
CREATE OR REPLACE VIEW analytics.v_absorcion_inicio_proyecto AS
WITH primeras AS (
    SELECT codigo_proyecto,min(fecha_venta_documental) AS primera_venta_documental
    FROM analytics.v_absorcion_ventas_ciclos
    WHERE calidad_ciclo IN ('ELEGIBLE','ANULADA_RETROSPECTIVAMENTE')
    GROUP BY codigo_proyecto
)
SELECT i.*,p.primera_venta_documental,
       least(i.fecha_ingreso_stock,date_trunc('month',p.primera_venta_documental)::date) AS fecha_ingreso_efectiva,
       CASE WHEN p.primera_venta_documental<i.fecha_ingreso_stock
            THEN 'Inicio adelantado al mes de la primera venta documental; se conserva fecha del adjunto. Incluye evidencia de ventas luego anuladas.'
            ELSE 'Inicio del adjunto, ajustado al primer día del mes' END AS observacion
FROM analytics.absorcion_inicio_proyecto i LEFT JOIN primeras p USING (codigo_proyecto);

CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_unidad AS
WITH cycles AS (
    SELECT codigo_unidad,
        count(*) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS ventas_elegibles,
        count(*) FILTER (WHERE calidad_ciclo NOT IN ('ELEGIBLE','SIN_VENTA_FECHADA','ANULADA_RETROSPECTIVAMENTE')) AS ciclos_revision,
        min(fecha_venta_validada) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS fecha_venta,
        min(codigo_proforma) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS codigo_proforma,
        min(metodo_fecha_venta) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS metodo_fecha_venta,
        max(refreshed_at) AS ultima_actualizacion_ciclos
    FROM analytics.v_absorcion_ventas_ciclos GROUP BY codigo_unidad
)
SELECT u.codigo_unidad,u.nombre_unidad,u.codigo_proyecto,i.nombre_proyecto,
       u.tipo_unidad,u.estado_comercial AS estado_comercial_actual,
       i.fecha_inicio_fuente,i.fecha_ingreso_efectiva AS fecha_ingreso_stock,
       CASE WHEN c.ventas_elegibles=1 THEN c.fecha_venta END AS fecha_venta,
       CASE WHEN c.ventas_elegibles=1 THEN c.codigo_proforma END AS codigo_proforma,
       CASE WHEN c.ventas_elegibles=1 THEN c.metodo_fecha_venta END AS metodo_fecha_venta,
       coalesce(c.ventas_elegibles,0) AS ventas_elegibles,
       coalesce(c.ciclos_revision,0) AS ciclos_revision,
       (coalesce(c.ventas_elegibles,0)>1 OR coalesce(c.ciclos_revision,0)>0
        OR (c.fecha_venta IS NULL AND lower(coalesce(u.estado_comercial,'')) LIKE '%vendid%')) AS requiere_revision,
       c.ultima_actualizacion_ciclos,
       'RECONSTRUIDO_RETROSPECTIVO_VENTAS_VIGENTES'::text AS metodo_stock,
       i.observacion AS observacion_inicio_proyecto
FROM core.dim_unidad u
JOIN analytics.v_absorcion_inicio_proyecto i USING (codigo_proyecto)
LEFT JOIN cycles c USING (codigo_unidad)
WHERE lower(trim(u.tipo_unidad)) IN
      ('departamento','departamento flat','departamento duplex','departamento dúplex','departamento triplex','departamento tríplex');

-- Función con corte explícito para reproducibilidad; mes actual parcial.
CREATE OR REPLACE FUNCTION analytics.absorcion_ventas_mensual(p_fecha_corte date)
RETURNS TABLE (
    periodo_mes date,codigo_proyecto text,nombre_proyecto text,fecha_corte date,
    mes_parcial boolean,total_departamentos bigint,stock_inicial bigint,
    ingresos_mes bigint,ventas_mes bigint,ventas_acumuladas bigint,stock_final bigint,
    absorcion_mensual numeric,absorcion_acumulada numeric,unidades_revision bigint
) LANGUAGE sql STABLE AS $$
WITH months AS (
    SELECT m::date AS periodo_mes,
        least((m+interval '1 month - 1 day')::date,p_fecha_corte) AS corte
    FROM generate_series(DATE '2024-01-01'::timestamp,
                         date_trunc('month',p_fecha_corte)::timestamp,interval '1 month') m
), base AS (
    SELECT m.periodo_mes,u.codigo_proyecto,u.nombre_proyecto,m.corte,
        count(*) AS total,
        count(*) FILTER (WHERE u.fecha_ingreso_stock<m.periodo_mes
            AND (u.fecha_venta IS NULL OR u.fecha_venta>=m.periodo_mes)) AS inicial,
        count(*) FILTER (WHERE u.fecha_ingreso_stock BETWEEN m.periodo_mes AND m.corte) AS ingresos,
        count(*) FILTER (WHERE u.fecha_venta BETWEEN m.periodo_mes AND m.corte) AS ventas,
        count(*) FILTER (WHERE u.fecha_venta<=m.corte) AS acumuladas,
        count(*) FILTER (WHERE u.fecha_ingreso_stock<=m.corte
            AND (u.fecha_venta IS NULL OR u.fecha_venta>m.corte)) AS final,
        count(*) FILTER (WHERE u.requiere_revision) AS revision
    FROM months m CROSS JOIN analytics.v_absorcion_ventas_unidad u
    GROUP BY m.periodo_mes,u.codigo_proyecto,u.nombre_proyecto,m.corte
)
SELECT periodo_mes,codigo_proyecto,nombre_proyecto,corte,
       corte<(periodo_mes+interval '1 month - 1 day')::date,
       total,inicial,ingresos,ventas,acumuladas,final,
       ventas::numeric/nullif(inicial+ingresos,0),
       CASE WHEN inicial+ingresos+acumuladas>0 THEN acumuladas::numeric/nullif(total,0) END,
       revision
FROM base;
$$;
CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_mensual AS
SELECT * FROM analytics.absorcion_ventas_mensual((CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date);

CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_revision AS
SELECT * FROM analytics.v_absorcion_ventas_unidad WHERE requiere_revision;

-- Proyectos fuera del adjunto permanecen visibles para control, sin inventar altas.
CREATE OR REPLACE VIEW analytics.v_absorcion_proyectos_sin_inicio AS
SELECT u.codigo_proyecto,count(*) AS departamentos
FROM core.dim_unidad u
LEFT JOIN analytics.absorcion_inicio_proyecto i USING (codigo_proyecto)
WHERE i.codigo_proyecto IS NULL AND lower(trim(u.tipo_unidad)) IN
 ('departamento','departamento flat','departamento duplex','departamento dúplex','departamento triplex','departamento tríplex')
GROUP BY u.codigo_proyecto;

-- Casos resueltos y pendientes, con comentarios; no contiene datos personales.
CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_observaciones AS
SELECT c.*,i.nombre_proyecto,i.fecha_inicio_fuente,
       i.fecha_ingreso_stock AS fecha_ingreso_adjunto,i.fecha_ingreso_efectiva,
       i.observacion AS observacion_inicio_proyecto,
       CASE WHEN u.ventas_elegibles>1 THEN 'Más de una venta vigente: unidad excluida del conteo hasta resolver duplicidad'
            WHEN u.requiere_revision THEN 'Unidad con incidencias pendientes; revisar detalle'
            ELSE 'Caso documentado; sin pendientes a nivel de unidad' END AS observacion_unidad
FROM analytics.v_absorcion_ventas_ciclos c
JOIN analytics.v_absorcion_inicio_proyecto i USING (codigo_proyecto)
JOIN analytics.v_absorcion_ventas_unidad u USING (codigo_unidad)
WHERE c.observacion<>'' OR i.fecha_ingreso_efectiva<i.fecha_ingreso_stock OR u.requiere_revision;
