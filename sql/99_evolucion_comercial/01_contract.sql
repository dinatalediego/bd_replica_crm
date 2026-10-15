-- Local only. Canonical eligibility, NP-A and retrospective cancellations inherited.
CREATE TABLE IF NOT EXISTS analytics.comercial_precio_observado (
 fecha_observacion date NOT NULL, codigo_unidad text NOT NULL,
 codigo_proyecto text NOT NULL, nombre_tipologia text, dormitorios numeric,
 area_total numeric, moneda text, precio_lista numeric,
 source_loaded_at timestamptz, registrado_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(fecha_observacion,codigo_unidad)
);
CREATE INDEX IF NOT EXISTS ix_comercial_precio_unidad_fecha
 ON analytics.comercial_precio_observado(codigo_unidad,fecha_observacion DESC);

CREATE TABLE IF NOT EXISTS analytics.comercial_unidad_mes (
 codigo_unidad text NOT NULL,codigo_proyecto text NOT NULL,nombre_proyecto text,
 periodo_mes date NOT NULL,mes_vida integer NOT NULL,mes_calendario integer NOT NULL,
 fecha_inicio date NOT NULL,fecha_corte date NOT NULL,mes_parcial boolean NOT NULL,
 nombre_tipologia text,dormitorios numeric,area_total numeric,area_relativa numeric,
 stock_inicial integer NOT NULL,venta_mes integer NOT NULL,stock_final integer NOT NULL,
 dias_exposicion integer NOT NULL,requiere_revision boolean NOT NULL,
 fecha_precio_observado date,moneda text,precio_m2 numeric,precio_relativo numeric,
 PRIMARY KEY(codigo_unidad,periodo_mes),
 CHECK(stock_inicial-venta_mes=stock_final),CHECK(dias_exposicion>=0)
);
CREATE INDEX IF NOT EXISTS ix_comercial_unidad_proyecto_mes
 ON analytics.comercial_unidad_mes(codigo_proyecto,periodo_mes);
CREATE TABLE IF NOT EXISTS analytics.comercial_proyecto_mes (
 codigo_proyecto text NOT NULL,nombre_proyecto text,periodo_mes date NOT NULL,
 mes_vida integer NOT NULL,mes_calendario integer NOT NULL,fecha_corte date NOT NULL,
 mes_parcial boolean NOT NULL,stock_lanzamiento bigint NOT NULL,
 stock_inicial bigint NOT NULL,ventas_mes bigint NOT NULL,ventas_acumuladas bigint NOT NULL,
 stock_final bigint NOT NULL,absorcion_mes numeric,absorcion_acumulada numeric,
 dias_exposicion bigint,ventas_por_30_dias_unidad numeric,unidades_revision bigint,
 PRIMARY KEY(codigo_proyecto,periodo_mes)
);

-- No accepts historical observation dates: observing today's CORE cannot backfill prices.
CREATE OR REPLACE FUNCTION analytics.refresh_evolucion_comercial()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE corte date := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('analytics.refresh_evolucion_comercial'));
 INSERT INTO analytics.comercial_precio_observado
 (fecha_observacion,codigo_unidad,codigo_proyecto,nombre_tipologia,dormitorios,
  area_total,moneda,precio_lista,source_loaded_at)
 SELECT corte,u.codigo_unidad,u.codigo_proyecto,d.nombre_tipologia,d.total_habitaciones,
 d.area_total,nullif(upper(btrim(d.moneda_precio_lista)),''),
 d.precio_lista_actual,d.source_loaded_at
 FROM analytics.v_absorcion_ventas_unidad u JOIN core.dim_unidad d USING(codigo_unidad)
 ON CONFLICT DO NOTHING;

 -- Transactional replacement of derived tables; price observations survive refresh.
 DELETE FROM analytics.comercial_unidad_mes;
 INSERT INTO analytics.comercial_unidad_mes
 WITH unidades AS (
  SELECT u.*,d.nombre_tipologia,d.total_habitaciones AS dormitorios,d.area_total,
   d.area_total/nullif(avg(d.area_total) FILTER(WHERE d.area_total>0)
    OVER(PARTITION BY u.codigo_proyecto,d.total_habitaciones),0) AS area_relativa
  FROM analytics.v_absorcion_ventas_unidad u JOIN core.dim_unidad d USING(codigo_unidad)
 ), proyectos AS (
  SELECT codigo_proyecto,min(fecha_ingreso_stock) AS inicio,
   CASE WHEN count(*) FILTER(WHERE fecha_venta IS NULL OR fecha_venta>corte)>0
    THEN corte ELSE least(max(fecha_venta),corte) END AS fin
  FROM unidades GROUP BY codigo_proyecto
 ), panel AS (
 SELECT u.codigo_unidad,u.codigo_proyecto,u.nombre_proyecto,m::date AS periodo_mes,
  (12*(extract(year FROM m)-extract(year FROM p.inicio))+
   extract(month FROM m)-extract(month FROM p.inicio)+1)::integer AS mes_vida,
  extract(month FROM m)::integer AS mes_calendario,p.inicio,corte AS fecha_corte,
  corte<(m+interval '1 month - 1 day')::date AS mes_parcial,
  u.nombre_tipologia,u.dormitorios,u.area_total,u.area_relativa,
  (u.fecha_venta IS NULL OR u.fecha_venta>=m::date)::integer AS stock_inicial,
  (u.fecha_venta BETWEEN m::date AND least(corte,(m+interval '1 month - 1 day')::date))::integer AS venta_nullable,
  (u.fecha_venta IS NULL OR u.fecha_venta>least(corte,(m+interval '1 month - 1 day')::date))::integer AS stock_final,
  greatest(0,least(corte,(m+interval '1 month - 1 day')::date,coalesce(u.fecha_venta,corte))-m::date+1) AS dias_exposicion,
  u.requiere_revision,pr.fecha_observacion,pr.moneda,
  CASE WHEN pr.precio_lista>0 AND pr.area_total>0 THEN pr.precio_lista/pr.area_total END AS precio_m2
 FROM unidades u JOIN proyectos p USING(codigo_proyecto)
 CROSS JOIN LATERAL generate_series(p.inicio::timestamp,date_trunc('month',p.fin)::timestamp,interval '1 month') m
 LEFT JOIN LATERAL (
  SELECT o.* FROM analytics.comercial_precio_observado o
  WHERE o.codigo_unidad=u.codigo_unidad AND o.fecha_observacion<m::date
  ORDER BY o.fecha_observacion DESC LIMIT 1
 ) pr ON true
 )
 SELECT codigo_unidad,codigo_proyecto,nombre_proyecto,periodo_mes,mes_vida,mes_calendario,
 inicio,fecha_corte,mes_parcial,nombre_tipologia,dormitorios,area_total,area_relativa,
 stock_inicial,coalesce(venta_nullable,0),stock_final,dias_exposicion,requiere_revision,
 fecha_observacion,moneda,precio_m2,
 CASE WHEN moneda IS NOT NULL THEN precio_m2/nullif(avg(precio_m2)
 FILTER(WHERE stock_inicial=1) OVER(PARTITION BY codigo_proyecto,periodo_mes,dormitorios,moneda),0) END
 FROM panel;

 DELETE FROM analytics.comercial_proyecto_mes;
 INSERT INTO analytics.comercial_proyecto_mes
 SELECT codigo_proyecto,max(nombre_proyecto),periodo_mes,max(mes_vida),max(mes_calendario),
 max(fecha_corte),bool_or(mes_parcial),count(*),sum(stock_inicial),sum(venta_mes),
 count(*)-sum(stock_final),sum(stock_final),sum(venta_mes)::numeric/nullif(sum(stock_inicial),0),
 (count(*)-sum(stock_final))::numeric/nullif(count(*),0),sum(dias_exposicion),
 30*sum(venta_mes)::numeric/nullif(sum(dias_exposicion),0),
 count(*) FILTER(WHERE requiere_revision)
 FROM analytics.comercial_unidad_mes GROUP BY codigo_proyecto,periodo_mes;
END; $$;

CREATE OR REPLACE VIEW analytics.v_comercial_composicion_mes AS
SELECT codigo_proyecto,periodo_mes,mes_vida,mes_calendario,nombre_tipologia,dormitorios,
 count(*) AS stock_lanzamiento,sum(stock_inicial) AS stock_inicial,
 sum(venta_mes) AS ventas_mes,sum(stock_final) AS stock_final,
 sum(venta_mes)::numeric/nullif(sum(stock_inicial),0) AS absorcion_mes,
 avg(area_total) AS area_media,avg(area_relativa) AS area_relativa_media,
 sum(dias_exposicion) AS dias_exposicion,bool_or(mes_parcial) AS mes_parcial,
 count(*) FILTER(WHERE requiere_revision) AS unidades_revision
FROM analytics.comercial_unidad_mes
GROUP BY codigo_proyecto,periodo_mes,mes_vida,mes_calendario,nombre_tipologia,dormitorios;

-- Descriptive calendar rate, NOT a causal/adjusted seasonal effect.
CREATE OR REPLACE VIEW analytics.v_comercial_calendario AS
SELECT codigo_proyecto,mes_calendario,count(*) AS meses_completos,
 sum(ventas_mes) AS ventas,sum(dias_exposicion) AS dias_exposicion,
 30*sum(ventas_mes)::numeric/nullif(sum(dias_exposicion),0) AS ventas_por_30_dias_unidad
FROM analytics.comercial_proyecto_mes WHERE NOT mes_parcial
GROUP BY codigo_proyecto,mes_calendario;

-- First observed month's basket remains fixed. No currency mixing or imputation.
-- Monthly observation = latest actual observation in that month, not fabricated month-end.
CREATE OR REPLACE VIEW analytics.v_comercial_indice_precios AS
WITH mensual AS (
 SELECT DISTINCT ON(codigo_unidad,date_trunc('month',fecha_observacion))
 codigo_unidad,codigo_proyecto,date_trunc('month',fecha_observacion)::date AS periodo_mes,
 fecha_observacion,moneda,precio_lista/nullif(area_total,0) AS precio_m2
 FROM analytics.comercial_precio_observado
 WHERE precio_lista>0 AND area_total>0 AND moneda IS NOT NULL
 ORDER BY codigo_unidad,date_trunc('month',fecha_observacion),fecha_observacion DESC
), bases AS (
 SELECT codigo_proyecto,moneda,min(periodo_mes) AS mes_base FROM mensual GROUP BY codigo_proyecto,moneda
), cesta AS (
 SELECT m.* FROM mensual m JOIN bases b USING(codigo_proyecto,moneda)
 WHERE m.periodo_mes=b.mes_base
), periodos AS (
 SELECT DISTINCT codigo_proyecto,moneda,periodo_mes FROM mensual
), ratios AS (
 SELECT p.codigo_proyecto,p.moneda,p.periodo_mes,c.periodo_mes AS mes_base,
 c.codigo_unidad,m.precio_m2/c.precio_m2 AS relativo,m.fecha_observacion
 FROM periodos p JOIN cesta c USING(codigo_proyecto,moneda)
 LEFT JOIN mensual m ON m.codigo_unidad=c.codigo_unidad AND m.codigo_proyecto=p.codigo_proyecto
 AND m.moneda=p.moneda AND m.periodo_mes=p.periodo_mes
)
SELECT codigo_proyecto,moneda,periodo_mes,mes_base,count(*) AS unidades_cesta,
 count(relativo) AS unidades_observadas,count(relativo)::numeric/count(*) AS cobertura,
 CASE WHEN count(relativo)=count(*) THEN 100*exp(avg(ln(relativo))) END AS indice_base_100,
 max(fecha_observacion) AS ultima_observacion,
 periodo_mes=date_trunc('month',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date)::date AS mes_parcial
FROM ratios GROUP BY codigo_proyecto,moneda,periodo_mes,mes_base;
