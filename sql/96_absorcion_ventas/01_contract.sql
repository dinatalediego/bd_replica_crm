-- Stock pendiente de venta reconstruido bajo el supuesto de alta por proyecto.
-- Las fechas de venta provienen de Phase B + reconciliación, nunca se recalculan.
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

-- Una fila por ciclo, incluso si su venta no es elegible. Sin PII.
CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_ciclos AS
SELECT c.codigo_unidad,c.codigo_proforma,c.codigo_proyecto,
       c.fecha_separacion,c.fecha_de_minuta,c.fecha_firma_legacy,
       c.fecha_venta_validada,c.metodo_fecha_venta,
       c.resultado_canonico,c.reconciliation_status,
       c.separacion_source_id,c.venta_source_id,c.datos_extras_fecha_minuta_id,
       c.refreshed_at,
       CASE
         WHEN c.codigo_proyecto IS DISTINCT FROM u.codigo_proyecto THEN 'PROYECTO_INCONSISTENTE'
         WHEN c.fecha_venta_documental IS NOT NULL AND c.fecha_venta_validada IS NULL THEN 'FECHA_INVALIDA'
         WHEN c.fecha_de_minuta IS NOT NULL AND c.fecha_venta_validada IS DISTINCT FROM c.fecha_de_minuta THEN 'PAGO_CI_NO_PRIORIZADO'
         WHEN c.fecha_venta_validada IS NULL AND c.venta_source_id IS NOT NULL AND c.resultado_ciclo <> 'CAIDA' THEN 'VENTA_SIN_FECHA_CONFIRMADA'
         WHEN c.fecha_venta_validada IS NULL THEN 'SIN_VENTA_FECHADA'
         WHEN c.metodo_fecha_venta = 'LEGACY_FECHA_FIRMA_PRE_2026'
              AND c.fecha_separacion >= DATE '2026-01-01' THEN 'LEGACY_2026_PROHIBIDO'
         WHEN NOT (
              (c.metodo_fecha_venta = 'FECHA_DE_MINUTA' AND c.fecha_de_minuta = c.fecha_venta_validada)
              OR (c.metodo_fecha_venta = 'LEGACY_FECHA_FIRMA_PRE_2026'
                  AND c.fecha_separacion < DATE '2026-01-01'
                  AND c.fecha_de_minuta IS NULL AND c.fecha_firma_legacy = c.fecha_venta_validada)
              ) IS TRUE THEN 'METODO_FECHA_INVALIDO'
         WHEN c.fecha_venta_validada < i.fecha_ingreso_stock THEN 'VENTA_ANTERIOR_INGRESO'
         WHEN c.resultado_canonico <> 'VENTA' OR c.reconciliation_status <> 'RECONCILED' THEN 'VENTA_NO_RECONCILIADA'
         ELSE 'ELEGIBLE'
       END AS calidad_ciclo
FROM analytics.v_absorcion_ventas_reconciliado c
JOIN core.dim_unidad u USING (codigo_unidad)
JOIN analytics.absorcion_inicio_proyecto i ON i.codigo_proyecto=u.codigo_proyecto
WHERE lower(trim(u.tipo_unidad)) IN
      ('departamento','departamento flat','departamento duplex','departamento dúplex','departamento triplex','departamento tríplex');

CREATE OR REPLACE VIEW analytics.v_absorcion_ventas_unidad AS
WITH cycles AS (
    SELECT codigo_unidad,
        count(*) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS ventas_elegibles,
        count(*) FILTER (WHERE calidad_ciclo NOT IN ('ELEGIBLE','SIN_VENTA_FECHADA')) AS ciclos_revision,
        min(fecha_venta_validada) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS fecha_venta,
        min(codigo_proforma) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS codigo_proforma,
        min(metodo_fecha_venta) FILTER (WHERE calidad_ciclo='ELEGIBLE') AS metodo_fecha_venta,
        max(refreshed_at) AS ultima_actualizacion_ciclos
    FROM analytics.v_absorcion_ventas_ciclos GROUP BY codigo_unidad
)
SELECT u.codigo_unidad,u.nombre_unidad,u.codigo_proyecto,i.nombre_proyecto,
       u.tipo_unidad,u.estado_comercial AS estado_comercial_actual,
       i.fecha_inicio_fuente,i.fecha_ingreso_stock,
       CASE WHEN c.ventas_elegibles=1 THEN c.fecha_venta END AS fecha_venta,
       CASE WHEN c.ventas_elegibles=1 THEN c.codigo_proforma END AS codigo_proforma,
       CASE WHEN c.ventas_elegibles=1 THEN c.metodo_fecha_venta END AS metodo_fecha_venta,
       coalesce(c.ventas_elegibles,0) AS ventas_elegibles,
       coalesce(c.ciclos_revision,0) AS ciclos_revision,
       (coalesce(c.ventas_elegibles,0)>1 OR coalesce(c.ciclos_revision,0)>0
        OR (c.fecha_venta IS NULL AND lower(coalesce(u.estado_comercial,'')) LIKE '%vendid%')) AS requiere_revision,
       c.ultima_actualizacion_ciclos,
       'RECONSTRUIDO_ALTA_PROYECTO_MENOS_VENTAS_VALIDADAS'::text AS metodo_stock
FROM core.dim_unidad u
JOIN analytics.absorcion_inicio_proyecto i USING (codigo_proyecto)
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
