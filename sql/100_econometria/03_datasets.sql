CREATE OR REPLACE FUNCTION analytics.build_econometric_datasets(p_backfill boolean DEFAULT false)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE hoy date := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date;
BEGIN
 DROP TABLE IF EXISTS pg_temp.econometric_current_events;
 CREATE TEMP TABLE econometric_current_events ON COMMIT DROP AS
 SELECT * FROM analytics.v_evento_comercial_actual WHERE activo AND fuente='ABSORCION_CICLOS';
 CREATE INDEX ON econometric_current_events(codigo_unidad,fecha_evento);
 ANALYZE econometric_current_events;
 IF p_backfill THEN
 -- Updatable diagnostic dataset; current characteristics and retrospectively revised sales.
 INSERT INTO features.dataset_unidad_prediccion
 SELECT m.codigo_unidad,m.codigo_proyecto,(m.periodo_mes+interval '1 month - 1 day')::date,
 'RECONSTRUIDO',clock_timestamp(),NULL,m.stock_final=1,
 jsonb_build_object('mes_vida',m.mes_vida,'mes_calendario',m.mes_calendario,
 'tipologia',m.nombre_tipologia,'dormitorios',m.dormitorios,'area_total',m.area_total,
 'area_relativa',m.area_relativa,'precio_m2',m.precio_m2,'moneda',m.moneda,
 'precio_relativo',m.precio_relativo,'fecha_precio',m.fecha_precio_observado,
 'vendio_mes',m.venta_mes,'dias_exposicion_reconstruidos',m.dias_exposicion),
 jsonb_build_object('point_in_time',false,'atributos_actuales',true,
 'disponibilidad_real_desconocida',true,'requiere_revision',m.requiere_revision)
 FROM analytics.comercial_unidad_mes m WHERE NOT m.mes_parcial
 ON CONFLICT(codigo_unidad,fecha_corte,evidencia) DO UPDATE SET
 captured_at=excluded.captured_at,pendiente_venta=excluded.pendiente_venta,
 features=excluded.features,calidad=excluded.calidad
 WHERE (dataset_unidad_prediccion.pendiente_venta,dataset_unidad_prediccion.features,dataset_unidad_prediccion.calidad)
 IS DISTINCT FROM (excluded.pendiente_venta,excluded.features,excluded.calidad);
 -- Remove obsolete reconstructed rows if the canonical project scope changes.
 DELETE FROM features.unidad_prediccion_resultado r WHERE r.evidencia='RECONSTRUIDO'
 AND NOT EXISTS(SELECT 1 FROM analytics.comercial_unidad_mes m WHERE m.codigo_unidad=r.codigo_unidad
 AND (m.periodo_mes+interval '1 month - 1 day')::date=r.fecha_corte AND NOT m.mes_parcial);
 DELETE FROM features.dataset_unidad_prediccion d WHERE d.evidencia='RECONSTRUIDO'
 AND NOT EXISTS(SELECT 1 FROM analytics.comercial_unidad_mes m WHERE m.codigo_unidad=d.codigo_unidad
 AND (m.periodo_mes+interval '1 month - 1 day')::date=d.fecha_corte AND NOT m.mes_parcial);
 END IF;

 INSERT INTO features.dataset_unidad_prediccion
 WITH base AS (
 SELECT s.*,s.area_total/nullif(avg(s.area_total) FILTER(WHERE s.area_total>0)
 OVER(PARTITION BY s.fecha_corte,s.codigo_proyecto,s.dormitorios),0) AS area_relativa,
 CASE WHEN s.precio_lista>0 AND s.area_total>0 THEN s.precio_lista/s.area_total END AS precio_m2
 FROM analytics.snapshot_unidad_diario s WHERE s.fecha_corte=hoy OR p_backfill
 ), ratios AS (
 SELECT b.*,CASE WHEN moneda IS NOT NULL THEN precio_m2/nullif(avg(precio_m2) FILTER(WHERE disponible)
 OVER(PARTITION BY fecha_corte,codigo_proyecto,dormitorios,moneda),0) END AS precio_relativo
 FROM base b
 )
 SELECT s.codigo_unidad,s.codigo_proyecto,s.fecha_corte,'OBSERVADO',s.captured_at,s.disponible,
 s.estado<>'VENDIDO',jsonb_build_object('estado',s.estado,'tipologia',s.nombre_tipologia,
 'dormitorios',s.dormitorios,'piso',s.piso,'area_total',s.area_total,'area_libre',s.area_libre,
 'area_relativa',s.area_relativa,'precio_lista',s.precio_lista,'precio_m2',s.precio_m2,
 'precio_relativo',s.precio_relativo,'moneda',s.moneda,'estado_construccion',s.estado_construccion,
 'mes_vida',12*(extract(year FROM s.fecha_corte)-extract(year FROM s.fecha_inicio))+
 extract(month FROM s.fecha_corte)-extract(month FROM s.fecha_inicio)+1,
 'mes_calendario',extract(month FROM s.fecha_corte),'demanda_4_semanas',dem.payload),
 jsonb_build_object('point_in_time',true,'requiere_revision',s.requiere_revision,
 'source_loaded_at',s.source_loaded_at,'source_fresh_48h',coalesce(s.source_loaded_at>=s.captured_at-interval '48 hours',false),
 'disponibilidad_clasificada',s.disponible IS NOT NULL)
 FROM ratios s LEFT JOIN LATERAL (
 SELECT jsonb_build_object('leads_creados',sum(leads_creados),'semanas_con_leads',count(leads_creados),'asignaciones',sum(asignaciones_clientes),'proformas',sum(proformas),
 'minutas_brutas',sum(minutas_brutas),'separaciones',sum(separaciones),
 'interacciones',sum(interacciones),'visitas',sum(visitas)) AS payload
 FROM analytics.panel_demanda_proyecto_semana w WHERE s.fecha_corte=hoy AND w.codigo_proyecto=s.codigo_proyecto
 AND w.semana>=date_trunc('week',s.fecha_corte)::date-28
 AND w.semana<date_trunc('week',s.fecha_corte)::date
 ) dem ON true
 ON CONFLICT DO NOTHING;

 -- Only score windows ending BEFORE today: today's ingestion is not a closed day.
 INSERT INTO features.unidad_prediccion_resultado
 (codigo_unidad,fecha_corte,evidencia,horizonte_dias,ventana_fin,maduro,
 primera_minuta,minutas_brutas,anulaciones,venta_vigente,calidad_resultado)
 SELECT d.codigo_unidad,d.fecha_corte,d.evidencia,h.h,d.fecha_corte+h.h,
 d.fecha_corte+h.h<hoy,
 CASE WHEN d.fecha_corte+h.h<hoy THEN e.primera END,
 CASE WHEN d.fecha_corte+h.h<hoy THEN e.minutas END,
 CASE WHEN d.fecha_corte+h.h<hoy THEN e.anulaciones END,
 CASE WHEN d.fecha_corte+h.h<hoy AND u.codigo_unidad IS NOT NULL THEN (coalesce(u.fecha_venta BETWEEN d.fecha_corte+1 AND d.fecha_corte+h.h,false))::integer END,
 jsonb_build_object('unidad_en_universo_actual',u.codigo_unidad IS NOT NULL,'requiere_revision',u.requiere_revision,'cierre_por_calendario',true,
 'source_fresh_48h',coalesce(current_d.source_loaded_at>=CURRENT_TIMESTAMP-interval '48 hours',false))
 FROM features.dataset_unidad_prediccion d CROSS JOIN(VALUES(30),(60),(90),(180)) h(h)
 LEFT JOIN analytics.v_absorcion_ventas_unidad u USING(codigo_unidad)
 LEFT JOIN core.dim_unidad current_d ON current_d.codigo_unidad=d.codigo_unidad
 LEFT JOIN LATERAL (
 SELECT min(fecha_evento) FILTER(WHERE tipo_evento='MINUTA') AS primera,
 count(*) FILTER(WHERE tipo_evento='MINUTA')::integer AS minutas,
 count(*) FILTER(WHERE tipo_evento='ANULACION')::integer AS anulaciones
 FROM econometric_current_events e WHERE e.codigo_unidad=d.codigo_unidad AND e.fecha_evento>d.fecha_corte AND e.fecha_evento<=d.fecha_corte+h.h
 ) e ON true
 ON CONFLICT(codigo_unidad,fecha_corte,evidencia,horizonte_dias) DO UPDATE SET
 maduro=excluded.maduro,primera_minuta=excluded.primera_minuta,minutas_brutas=excluded.minutas_brutas,
 anulaciones=excluded.anulaciones,venta_vigente=excluded.venta_vigente,calidad_resultado=excluded.calidad_resultado,medido_at=clock_timestamp()
 WHERE (unidad_prediccion_resultado.maduro,unidad_prediccion_resultado.primera_minuta,
 unidad_prediccion_resultado.minutas_brutas,unidad_prediccion_resultado.anulaciones,
 unidad_prediccion_resultado.venta_vigente,unidad_prediccion_resultado.calidad_resultado)
 IS DISTINCT FROM (excluded.maduro,excluded.primera_minuta,excluded.minutas_brutas,
 excluded.anulaciones,excluded.venta_vigente,excluded.calidad_resultado);
END $$;

CREATE OR REPLACE VIEW features.v_dataset_unidad_entrenamiento AS
SELECT d.*,r.horizonte_dias,r.ventana_fin,r.maduro,r.primera_minuta,r.minutas_brutas,
 r.anulaciones,r.venta_vigente,r.medido_at,
 (d.evidencia='OBSERVADO' AND d.disponible IS TRUE AND r.maduro
 AND coalesce((d.calidad->>'source_fresh_48h')::boolean,false)
 AND NOT coalesce((d.calidad->>'requiere_revision')::boolean,true)
 AND coalesce((r.calidad_resultado->>'unidad_en_universo_actual')::boolean,false)
 AND NOT coalesce((r.calidad_resultado->>'requiere_revision')::boolean,true)
 AND coalesce((r.calidad_resultado->>'source_fresh_48h')::boolean,false)) AS elegible_validacion_prospectiva
FROM features.dataset_unidad_prediccion d JOIN features.unidad_prediccion_resultado r
USING(codigo_unidad,fecha_corte,evidencia);

CREATE OR REPLACE VIEW analytics.v_econometria_cobertura AS
SELECT d.evidencia,d.codigo_proyecto,min(d.fecha_corte) AS primer_corte,max(d.fecha_corte) AS ultimo_corte,
 count(*) AS filas,count(*) FILTER(WHERE d.disponible) AS filas_disponibles,
 count(*) FILTER(WHERE d.features->>'precio_m2' IS NOT NULL) AS filas_precio,
 count(*) FILTER(WHERE coalesce((d.calidad->>'requiere_revision')::boolean,false)) AS filas_revision
FROM features.dataset_unidad_prediccion d GROUP BY 1,2;

CREATE OR REPLACE VIEW analytics.v_econometria_precios_relativos AS
SELECT codigo_unidad,codigo_proyecto,fecha_corte,evidencia,disponible,
 features->>'tipologia' AS tipologia,(features->>'dormitorios')::numeric AS dormitorios,
 (features->>'area_total')::numeric AS area_total,(features->>'area_relativa')::numeric AS area_relativa,
 features->>'moneda' AS moneda,(features->>'precio_m2')::numeric AS precio_m2,
 (features->>'precio_relativo')::numeric AS precio_relativo,calidad
FROM features.dataset_unidad_prediccion;
