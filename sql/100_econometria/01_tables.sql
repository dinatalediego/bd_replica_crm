CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS model_control;
CREATE TABLE IF NOT EXISTS model_control.econometria_runs (
 run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),finished_at timestamptz,
 status text NOT NULL CHECK(status IN ('RUNNING','OK','FAILED')),
 backfill boolean NOT NULL, detail jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS analytics.fact_evento_comercial (
 version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 event_key text NOT NULL,codigo_unidad text NOT NULL,codigo_proyecto text NOT NULL,
 codigo_proforma text,tipo_evento text NOT NULL,fecha_evento date,
 fecha_registro_origen timestamptz,disponible_desde timestamptz NOT NULL DEFAULT clock_timestamp(),
 fuente text NOT NULL,evidencia text NOT NULL,activo boolean NOT NULL,
 payload jsonb NOT NULL, UNIQUE(event_key,disponible_desde)
);
CREATE INDEX IF NOT EXISTS ix_econom_event_key ON analytics.fact_evento_comercial(event_key,version_id DESC);
CREATE INDEX IF NOT EXISTS ix_econom_event_unit ON analytics.fact_evento_comercial(codigo_unidad,fecha_evento);
CREATE OR REPLACE VIEW analytics.v_evento_comercial_actual AS
SELECT DISTINCT ON(event_key) * FROM analytics.fact_evento_comercial ORDER BY event_key,version_id DESC;

CREATE TABLE IF NOT EXISTS analytics.snapshot_unidad_diario (
 fecha_corte date NOT NULL,codigo_unidad text NOT NULL,codigo_proyecto text NOT NULL,
 captured_at timestamptz NOT NULL,estado text NOT NULL,disponible boolean,
 nombre_tipologia text,dormitorios numeric,piso text,area_total numeric,area_libre numeric,
 precio_lista numeric,moneda text,fecha_inicio date,estado_construccion text,
 fuente text NOT NULL,source_loaded_at timestamptz,requiere_revision boolean NOT NULL,
 PRIMARY KEY(fecha_corte,codigo_unidad)
);
CREATE TABLE IF NOT EXISTS analytics.historial_oferta_unidad (
 version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo_unidad text NOT NULL,codigo_proyecto text NOT NULL,tipo_precio text NOT NULL
 CHECK(tipo_precio IN ('LISTA','OFERTADO','CIERRE')),
 fecha_referencia date NOT NULL,disponible_desde timestamptz NOT NULL,
 precio numeric CHECK(precio>0),moneda text,area_total numeric,descuento numeric,
 fuente text NOT NULL,clave_fuente text NOT NULL,calidad text NOT NULL,
 ingested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(fuente,clave_fuente,tipo_precio)
);
CREATE INDEX IF NOT EXISTS ix_econom_offer_asof ON analytics.historial_oferta_unidad(codigo_unidad,disponible_desde DESC);
CREATE TABLE IF NOT EXISTS analytics.historial_etapa_proyecto (
 version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 codigo_proyecto text NOT NULL,fecha_referencia date NOT NULL,
 disponible_desde timestamptz NOT NULL DEFAULT clock_timestamp(),
 composicion_etapas jsonb NOT NULL,fuente text NOT NULL
);
CREATE TABLE IF NOT EXISTS analytics.intervencion_comercial (
 clave_fuente text PRIMARY KEY,codigo_proyecto text NOT NULL,tipo text NOT NULL,
 inicio date NOT NULL,fin date,disponible_desde timestamptz NOT NULL,
 descripcion text NOT NULL,inversion numeric CHECK(inversion>=0),moneda text,
 fuente text NOT NULL,ingested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(fin IS NULL OR fin>=inicio)
);
CREATE TABLE IF NOT EXISTS analytics.contexto_mercado_mes (
 mercado text NOT NULL,indicador text NOT NULL,periodo_mes date NOT NULL,
 publicado_at timestamptz NOT NULL,valor numeric NOT NULL,unidad text NOT NULL,
 fuente text NOT NULL,ingested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(mercado,indicador,periodo_mes,publicado_at),
 CHECK(periodo_mes=date_trunc('month',periodo_mes)::date)
);
CREATE TABLE IF NOT EXISTS analytics.panel_demanda_proyecto_semana (
 codigo_proyecto text NOT NULL,semana date NOT NULL,
 asignaciones_clientes bigint,clientes_unicos_asignados bigint,proformas bigint,
 leads_creados bigint,clientes_unicos_creados bigint,
 interacciones bigint,visitas bigint,separaciones bigint NOT NULL,
 minutas_brutas bigint NOT NULL,anulaciones bigint NOT NULL,
 fuentes jsonb NOT NULL,revisado_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(codigo_proyecto,semana)
);
CREATE TABLE IF NOT EXISTS features.dataset_unidad_prediccion (
 codigo_unidad text NOT NULL,codigo_proyecto text NOT NULL,fecha_corte date NOT NULL,
 evidencia text NOT NULL CHECK(evidencia IN ('RECONSTRUIDO','OBSERVADO')),
 captured_at timestamptz NOT NULL,disponible boolean,pendiente_venta boolean NOT NULL,
 features jsonb NOT NULL,calidad jsonb NOT NULL,
 PRIMARY KEY(codigo_unidad,fecha_corte,evidencia)
);
CREATE TABLE IF NOT EXISTS features.unidad_prediccion_resultado (
 codigo_unidad text NOT NULL,fecha_corte date NOT NULL,evidencia text NOT NULL,
 horizonte_dias integer NOT NULL CHECK(horizonte_dias IN(30,60,90,180)),
 ventana_fin date NOT NULL,maduro boolean NOT NULL,
 primera_minuta date,minutas_brutas integer,anulaciones integer,venta_vigente integer,
 medido_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 calidad_resultado jsonb NOT NULL DEFAULT '{}',
 PRIMARY KEY(codigo_unidad,fecha_corte,evidencia,horizonte_dias),
 FOREIGN KEY(codigo_unidad,fecha_corte,evidencia)
 REFERENCES features.dataset_unidad_prediccion,
 CHECK(maduro OR (primera_minuta IS NULL AND minutas_brutas IS NULL AND anulaciones IS NULL AND venta_vigente IS NULL))
);
CREATE TABLE IF NOT EXISTS model_control.econometria_fuentes (
 fuente text PRIMARY KEY,estado text NOT NULL,detalle text NOT NULL,
 checked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Append-only evidence, including source corrections as NEW event versions.
CREATE OR REPLACE FUNCTION model_control.protect_econometric_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'Evidencia inmutable: insertar una nueva version'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['analytics.fact_evento_comercial','analytics.snapshot_unidad_diario',
 'analytics.historial_oferta_unidad','analytics.historial_etapa_proyecto',
 'analytics.contexto_mercado_mes','analytics.intervencion_comercial'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=t::regclass AND tgname='econometric_append_only') THEN
 EXECUTE format('CREATE TRIGGER econometric_append_only BEFORE UPDATE OR DELETE ON %s FOR EACH ROW EXECUTE FUNCTION model_control.protect_econometric_evidence()',t);
 END IF; END LOOP;
END $$;
CREATE OR REPLACE FUNCTION model_control.protect_observed_features()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF OLD.evidencia='OBSERVADO' THEN RAISE EXCEPTION 'Corte observado inmutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='features.dataset_unidad_prediccion'::regclass AND tgname='observed_features_immutable') THEN
 CREATE TRIGGER observed_features_immutable BEFORE UPDATE OR DELETE ON features.dataset_unidad_prediccion
 FOR EACH ROW EXECUTE FUNCTION model_control.protect_observed_features();
 END IF;
END $$;
