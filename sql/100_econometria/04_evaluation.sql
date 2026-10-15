CREATE TABLE IF NOT EXISTS features.unidad_resultado_version (
 version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo_unidad text NOT NULL,fecha_corte date NOT NULL,evidencia text NOT NULL,
 horizonte_dias integer NOT NULL,medido_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 resultado jsonb NOT NULL
);
CREATE OR REPLACE FUNCTION features.audit_unidad_resultado()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='INSERT' OR (to_jsonb(NEW)-'medido_at') IS DISTINCT FROM (to_jsonb(OLD)-'medido_at') THEN
 INSERT INTO features.unidad_resultado_version(codigo_unidad,fecha_corte,evidencia,horizonte_dias,resultado)
 VALUES(NEW.codigo_unidad,NEW.fecha_corte,NEW.evidencia,NEW.horizonte_dias,to_jsonb(NEW));
 END IF; RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='features.unidad_prediccion_resultado'::regclass AND tgname='audit_resultado') THEN
 CREATE TRIGGER audit_resultado AFTER INSERT OR UPDATE ON features.unidad_prediccion_resultado
 FOR EACH ROW EXECUTE FUNCTION features.audit_unidad_resultado(); END IF;
END $$;
CREATE TABLE IF NOT EXISTS model_control.prediccion_unidad (
 prediction_id text PRIMARY KEY,modelo text NOT NULL,version_modelo text NOT NULL,
 codigo_unidad text NOT NULL,fecha_corte date NOT NULL,evidencia text NOT NULL CHECK(evidencia='OBSERVADO'),
 horizonte_dias integer NOT NULL CHECK(horizonte_dias IN(30,60,90,180)),
 objetivo text NOT NULL CHECK(objetivo='MINUTA_BRUTA_AL_MENOS_UNA'),
 probabilidad numeric NOT NULL CHECK(probabilidad BETWEEN 0 AND 1),
 emitido_at timestamptz NOT NULL DEFAULT clock_timestamp(),escenario jsonb NOT NULL DEFAULT '{}',
 FOREIGN KEY(codigo_unidad,fecha_corte,evidencia) REFERENCES features.dataset_unidad_prediccion
);
CREATE OR REPLACE VIEW analytics.v_prediccion_unidad_evaluacion AS
WITH primera AS (
 SELECT DISTINCT ON(codigo_unidad,fecha_corte,evidencia,horizonte_dias) *
 FROM features.unidad_resultado_version WHERE (resultado->>'maduro')::boolean
 AND coalesce((resultado->'calidad_resultado'->>'unidad_en_universo_actual')::boolean,false)
 AND coalesce((resultado->'calidad_resultado'->>'source_fresh_48h')::boolean,false)
 AND NOT coalesce((resultado->'calidad_resultado'->>'requiere_revision')::boolean,true)
 ORDER BY codigo_unidad,fecha_corte,evidencia,horizonte_dias,version_id
)
SELECT p.*,r.version_id AS version_resultado,r.medido_at,
 CASE WHEN r.version_id IS NOT NULL THEN ((r.resultado->>'minutas_brutas')::integer>0)::integer END AS resultado,
 CASE WHEN r.version_id IS NOT NULL THEN
 power(p.probabilidad-((r.resultado->>'minutas_brutas')::integer>0)::integer,2) END AS brier,
 p.emitido_at < ((p.fecha_corte+1)::timestamp AT TIME ZONE 'America/Lima') AS emitido_antes_ventana,
 r.resultado->'calidad_resultado' AS calidad_resultado,
 coalesce((r.resultado->'calidad_resultado'->>'unidad_en_universo_actual')::boolean,false)
 AND NOT coalesce((r.resultado->'calidad_resultado'->>'requiere_revision')::boolean,true) AS resultado_sin_alertas
FROM model_control.prediccion_unidad p LEFT JOIN primera r USING(codigo_unidad,fecha_corte,evidencia,horizonte_dias);
CREATE OR REPLACE FUNCTION model_control.validate_unidad_prediction()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 -- Caller timestamps cannot establish historical evidence; database time is authoritative.
 NEW.emitido_at := clock_timestamp();
 IF NEW.fecha_corte<>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date THEN
 RAISE EXCEPTION 'El corte prospectivo debe corresponder al dia actual'; END IF;
 IF NEW.emitido_at >= ((NEW.fecha_corte+1)::timestamp AT TIME ZONE 'America/Lima') THEN
 RAISE EXCEPTION 'No se puede emitir retrospectivamente una prediccion prospectiva'; END IF;
 IF NOT EXISTS(SELECT 1 FROM features.dataset_unidad_prediccion d
 WHERE d.codigo_unidad=NEW.codigo_unidad AND d.fecha_corte=NEW.fecha_corte AND d.evidencia='OBSERVADO'
 AND d.disponible IS TRUE AND d.captured_at<=NEW.emitido_at) THEN
 RAISE EXCEPTION 'Falta corte observado disponible previo a la prediccion'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='model_control.prediccion_unidad'::regclass AND tgname='validate_unit_prediction') THEN
 CREATE TRIGGER validate_unit_prediction BEFORE INSERT ON model_control.prediccion_unidad
 FOR EACH ROW EXECUTE FUNCTION model_control.validate_unidad_prediction(); END IF;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['features.unidad_resultado_version','model_control.prediccion_unidad'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=t::regclass AND tgname='econometric_append_only') THEN
 EXECUTE format('CREATE TRIGGER econometric_append_only BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION model_control.protect_econometric_evidence()',t);
 END IF; END LOOP;
END $$;
-- Reuse project forecast registries and frozen outcomes already used by the forecasting pilot.
CREATE OR REPLACE VIEW analytics.registro_prediccion_resultado AS
SELECT * FROM analytics.v_commercial_forecast_performance;

-- Point-in-time joins for external variables: publication AND local ingestion must precede the cut.
CREATE TABLE IF NOT EXISTS analytics.proyecto_mercado_econometria (
 codigo_proyecto text PRIMARY KEY,mercado text NOT NULL
);
CREATE OR REPLACE VIEW features.v_contexto_mercado_por_corte AS
SELECT DISTINCT ON(d.codigo_proyecto,d.fecha_corte,d.evidencia,m.indicador)
 d.codigo_proyecto,d.fecha_corte,d.evidencia,m.indicador,m.periodo_mes,m.valor,m.unidad,m.publicado_at,m.fuente
FROM (SELECT codigo_proyecto,fecha_corte,evidencia,min(captured_at) AS captured_at
 FROM features.dataset_unidad_prediccion GROUP BY 1,2,3) d
JOIN analytics.proyecto_mercado_econometria p USING(codigo_proyecto)
JOIN analytics.contexto_mercado_mes m ON m.mercado=p.mercado
 AND m.publicado_at<=d.captured_at
 AND m.periodo_mes<=d.fecha_corte
 AND (d.evidencia='RECONSTRUIDO' OR m.ingested_at<=d.captured_at)
 AND (d.evidencia='OBSERVADO' OR (m.publicado_at AT TIME ZONE 'America/Lima')::date<=d.fecha_corte)
ORDER BY d.codigo_proyecto,d.fecha_corte,d.evidencia,m.indicador,m.periodo_mes DESC,m.publicado_at DESC;

-- Observed nominal series: never treats an imported/backdated quote as an observed old price.
CREATE OR REPLACE VIEW analytics.v_econometria_serie_precios AS
WITH mensual AS (
 SELECT DISTINCT ON(codigo_unidad,tipo_precio,date_trunc('month',disponible_desde AT TIME ZONE 'America/Lima'))
 codigo_unidad,codigo_proyecto,tipo_precio,moneda,
 date_trunc('month',disponible_desde AT TIME ZONE 'America/Lima')::date AS mes,
 precio/area_total AS precio_m2
 FROM analytics.historial_oferta_unidad
 WHERE precio>0 AND area_total>0 AND moneda IS NOT NULL
 AND calidad IN('OBSERVADO','OBSERVADO_EN_REGISTRADO_AT')
 ORDER BY codigo_unidad,tipo_precio,date_trunc('month',disponible_desde AT TIME ZONE 'America/Lima'),disponible_desde DESC,version_id DESC
), bases AS (
 SELECT codigo_proyecto,tipo_precio,moneda,min(mes) AS mes_base FROM mensual GROUP BY 1,2,3
), cesta AS (
 SELECT m.* FROM mensual m JOIN bases b USING(codigo_proyecto,tipo_precio,moneda) WHERE m.mes=b.mes_base
), periodos AS (SELECT DISTINCT codigo_proyecto,tipo_precio,moneda,mes FROM mensual)
SELECT p.codigo_proyecto,p.tipo_precio,p.moneda,p.mes,c.mes AS mes_base,count(*) AS unidades_cesta,
 count(m.precio_m2)::numeric/count(*) AS cobertura,
 CASE WHEN count(m.precio_m2)=count(*) THEN 100*exp(avg(ln(m.precio_m2/c.precio_m2))) END AS indice_base_100
FROM periodos p JOIN cesta c USING(codigo_proyecto,tipo_precio,moneda)
LEFT JOIN mensual m ON m.codigo_unidad=c.codigo_unidad AND m.codigo_proyecto=p.codigo_proyecto
 AND m.tipo_precio=p.tipo_precio AND m.moneda=p.moneda AND m.mes=p.mes
GROUP BY p.codigo_proyecto,p.tipo_precio,p.moneda,p.mes,c.mes;

CREATE OR REPLACE VIEW features.v_estacionalidad_panel AS
SELECT p.*,
 extract(year FROM p.periodo_mes)::integer AS anio_calendario,
 extract(day FROM p.periodo_mes+interval '1 month - 1 day')::integer AS dias_mes,
 comp.dormitorios_promedio_stock,comp.area_promedio_stock,
 comp.fraccion_1_dormitorio,comp.fraccion_2_dormitorios,comp.fraccion_3_mas_dormitorios,
 'RECONSTRUIDO_ATRIBUTOS_ACTUALES'::text AS evidencia
FROM analytics.comercial_proyecto_mes p
LEFT JOIN LATERAL (
 SELECT avg(dormitorios) FILTER(WHERE stock_inicial=1) AS dormitorios_promedio_stock,
 avg(area_total) FILTER(WHERE stock_inicial=1) AS area_promedio_stock,
 count(*) FILTER(WHERE stock_inicial=1 AND dormitorios=1)::numeric/nullif(sum(stock_inicial),0) AS fraccion_1_dormitorio,
 count(*) FILTER(WHERE stock_inicial=1 AND dormitorios=2)::numeric/nullif(sum(stock_inicial),0) AS fraccion_2_dormitorios,
 count(*) FILTER(WHERE stock_inicial=1 AND dormitorios>=3)::numeric/nullif(sum(stock_inicial),0) AS fraccion_3_mas_dormitorios
 FROM analytics.comercial_unidad_mes u WHERE u.codigo_proyecto=p.codigo_proyecto AND u.periodo_mes=p.periodo_mes
) comp ON true;
