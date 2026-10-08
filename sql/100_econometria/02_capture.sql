CREATE OR REPLACE FUNCTION analytics.capture_econometric_events()
RETURNS void LANGUAGE plpgsql AS $$ BEGIN
 DROP TABLE IF EXISTS pg_temp.econom_events;
 CREATE TEMP TABLE econom_events ON COMMIT DROP AS
 WITH canonical AS (
 SELECT 'CICLO|'||c.codigo_unidad||'|'||c.codigo_proforma||'|'||e.tipo AS event_key,
 c.codigo_unidad,c.codigo_proyecto,c.codigo_proforma,e.tipo AS tipo_evento,e.fecha AS fecha_evento,
 'ABSORCION_CICLOS'::text AS fuente,'HISTORICO_DOCUMENTAL_REVISADO'::text AS evidencia,
 jsonb_build_object('calidad',c.calidad_ciclo,'metodo',c.metodo_fecha_venta) AS payload
 FROM analytics.v_absorcion_ventas_ciclos c
 CROSS JOIN LATERAL(VALUES
 ('SEPARACION',c.fecha_separacion_raw),
 ('MINUTA',CASE WHEN c.calidad_ciclo IN('ELEGIBLE','ANULADA_RETROSPECTIVAMENTE') THEN c.fecha_venta_documental END),
 ('ANULACION',c.fecha_anulacion)) e(tipo,fecha)
 WHERE e.fecha IS NOT NULL AND e.fecha<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
 ), ledger AS (
 SELECT 'LEDGER|'||l.movement_id,l.codigo_unidad,u.codigo_proyecto,l.codigo_proforma,
 l.tipo_evento,l.fecha_evento,'LEDGER_TRANSICION','HISTORICO_LEDGER_COBERTURA_PARCIAL',
 jsonb_build_object('estado_anterior',l.estado_anterior,'estado_nuevo',l.estado_nuevo,
 'delta_stock',l.delta_stock,'source_event_key',l.source_event_key)
 FROM analytics.fact_movimientos_stock l JOIN analytics.v_absorcion_ventas_unidad u USING(codigo_unidad)
 WHERE l.transition_applied AND l.fecha_evento<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
 ) SELECT * FROM canonical UNION ALL SELECT * FROM ledger;
 -- An ambiguous source key is an error, never silently select a random row.
 CREATE UNIQUE INDEX ON econom_events(event_key);
 INSERT INTO analytics.fact_evento_comercial
 (event_key,codigo_unidad,codigo_proyecto,codigo_proforma,tipo_evento,fecha_evento,fuente,evidencia,activo,payload)
 SELECT s.* FROM (SELECT e.event_key,e.codigo_unidad,e.codigo_proyecto,
 e.codigo_proforma,e.tipo_evento,e.fecha_evento,e.fuente,e.evidencia,true AS activo,e.payload
 FROM econom_events e LEFT JOIN analytics.v_evento_comercial_actual old USING(event_key)
 WHERE old.event_key IS NULL OR NOT old.activo OR
 (old.fecha_evento,old.payload,old.codigo_proyecto) IS DISTINCT FROM (e.fecha_evento,e.payload,e.codigo_proyecto)) s;
 INSERT INTO analytics.fact_evento_comercial
 (event_key,codigo_unidad,codigo_proyecto,codigo_proforma,tipo_evento,fecha_evento,fuente,evidencia,activo,payload)
 SELECT old.event_key,old.codigo_unidad,old.codigo_proyecto,old.codigo_proforma,old.tipo_evento,
 old.fecha_evento,old.fuente,old.evidencia,false,old.payload
 FROM analytics.v_evento_comercial_actual old
 WHERE old.activo AND old.fuente IN('ABSORCION_CICLOS','LEDGER_TRANSICION')
 AND NOT EXISTS(SELECT 1 FROM econom_events e WHERE e.event_key=old.event_key);
END $$;

CREATE OR REPLACE FUNCTION analytics.capture_econometric_current()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE hoy date := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date;
BEGIN
 INSERT INTO analytics.snapshot_unidad_diario
 SELECT hoy,u.codigo_unidad,u.codigo_proyecto,clock_timestamp(),
 CASE WHEN u.fecha_venta<=hoy THEN 'VENDIDO'
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('no disponible','no_disponible','bloqueado','bloqueada') THEN 'BLOQUEADO'
      WHEN lower(btrim(coalesce(d.estado_personalizado,''))) LIKE '%bloque%' THEN 'BLOQUEADO'
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('disponible','disponibles') THEN 'DISPONIBLE'
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('separado','separada') THEN 'SEPARADO'
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('vendido','vendida') THEN 'VENDIDO'
      ELSE 'DESCONOCIDO' END,
 CASE WHEN u.fecha_venta<=hoy THEN false
      WHEN lower(btrim(coalesce(d.estado_personalizado,''))) LIKE '%bloque%' THEN false
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('disponible','disponibles') THEN true
      WHEN lower(btrim(coalesce(d.estado_comercial,''))) IN('no disponible','no_disponible','bloqueado','bloqueada','separado','separada','vendido','vendida') THEN false
      ELSE NULL END,
 d.nombre_tipologia,d.total_habitaciones,d.piso,d.area_total,d.area_libre,
 d.precio_lista_actual,nullif(upper(btrim(d.moneda_precio_lista)),''),u.fecha_ingreso_stock,
 d.estado_construccion,'CORE_OBSERVADO',d.source_loaded_at,u.requiere_revision
 FROM analytics.v_absorcion_ventas_unidad u JOIN core.dim_unidad d USING(codigo_unidad)
 WHERE u.fecha_ingreso_stock<=hoy ON CONFLICT DO NOTHING;

 INSERT INTO analytics.historial_oferta_unidad
 (codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,
 area_total,fuente,clave_fuente,calidad)
 SELECT codigo_unidad,codigo_proyecto,'LISTA',fecha_corte,captured_at,
 CASE WHEN precio_lista>0 THEN precio_lista END,moneda,area_total,
 'SNAPSHOT_DIARIO',codigo_unidad||'|'||fecha_corte::text,
 CASE WHEN precio_lista>0 AND moneda IS NOT NULL THEN 'OBSERVADO' ELSE 'INCOMPLETO' END
 FROM analytics.snapshot_unidad_diario WHERE fecha_corte=hoy ON CONFLICT DO NOTHING;

 INSERT INTO analytics.historial_etapa_proyecto(codigo_proyecto,fecha_referencia,composicion_etapas,fuente)
 WITH counts AS (
 SELECT codigo_proyecto,coalesce(estado_construccion,'DESCONOCIDO') AS etapa,count(*) AS n
 FROM analytics.snapshot_unidad_diario WHERE fecha_corte=hoy GROUP BY 1,2
 ), payload AS (SELECT codigo_proyecto,jsonb_object_agg(etapa,n) AS etapas FROM counts GROUP BY 1)
 SELECT p.codigo_proyecto,hoy,p.etapas,'CORE_ESTADO_CONSTRUCCION'
 FROM payload p LEFT JOIN LATERAL (SELECT h.composicion_etapas FROM analytics.historial_etapa_proyecto h
 WHERE h.codigo_proyecto=p.codigo_proyecto ORDER BY version_id DESC LIMIT 1) old ON true
 WHERE old.composicion_etapas IS DISTINCT FROM p.etapas;
END $$;

-- Historical price snapshots are evidence at their captured_at, not at a supplied/backdated label.
CREATE OR REPLACE FUNCTION analytics.backfill_econometric_prices()
RETURNS void LANGUAGE plpgsql AS $$ BEGIN
 INSERT INTO analytics.historial_oferta_unidad
 (codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,
 area_total,fuente,clave_fuente,calidad)
 SELECT codigo_unidad,codigo_proyecto,'LISTA',fecha_observacion,registrado_at,
 CASE WHEN precio_lista>0 THEN precio_lista END,moneda,area_total,
 'COMERCIAL_PRECIO_OBSERVADO',codigo_unidad||'|'||fecha_observacion::text,'OBSERVADO_EN_REGISTRADO_AT'
 FROM analytics.comercial_precio_observado ON CONFLICT DO NOTHING;
 -- Existing pricing mart permits date overrides and defaults currency. Preserve that limitation.
 IF to_regclass('pricing_analytics.fact_precio_unidad_diario') IS NOT NULL THEN
 EXECUTE $q$
 INSERT INTO analytics.historial_oferta_unidad
 (codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,
 area_total,fuente,clave_fuente,calidad)
 SELECT p.codigo_unidad,p.codigo_proyecto,'LISTA',p.snapshot_date,p.captured_at,p.precio_lista,
 p.moneda,p.area_total,'PRICING_SNAPSHOT',p.unidad_fuente_key||'|'||p.snapshot_date::text,
 'LEGACY_MONEDA_Y_FECHA_REQUIEREN_REVISION'
 FROM pricing_analytics.fact_precio_unidad_diario p
 JOIN analytics.v_absorcion_ventas_unidad u ON u.codigo_unidad=p.codigo_unidad
 WHERE p.esquema_fuente='raw_cygnus' AND p.precio_lista>0
 ON CONFLICT DO NOTHING
 $q$;
 END IF;
END $$;

CREATE OR REPLACE FUNCTION analytics.backfill_econometric_stock()
RETURNS void LANGUAGE plpgsql AS $$ BEGIN
 IF to_regclass('analytics.fact_stock_snapshot_diario_unidad') IS NOT NULL THEN
 EXECUTE $q$
 INSERT INTO analytics.snapshot_unidad_diario
 (fecha_corte,codigo_unidad,codigo_proyecto,captured_at,estado,disponible,
 fecha_inicio,fuente,requiere_revision)
 SELECT s.fecha_snapshot,s.codigo_unidad,s.codigo_proyecto,s.captured_at,
 s.estado_comercial_consolidado,s.flag_disponible,u.fecha_ingreso_stock,
 'LEGACY_STOCK_OBSERVADO_AT',true
 FROM analytics.fact_stock_snapshot_diario_unidad s
 JOIN analytics.v_absorcion_ventas_unidad u USING(codigo_unidad)
 WHERE s.flag_departamento AND (s.captured_at AT TIME ZONE 'America/Lima')::date=s.fecha_snapshot
 AND s.fecha_snapshot<(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date
 ON CONFLICT DO NOTHING
 $q$;
 END IF;
END $$;
