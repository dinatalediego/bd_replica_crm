DO $$ DECLARE n integer; BEGIN
 ASSERT (SELECT count(*)=6 FROM analytics.fact_evento_comercial),'canonical + ledger retained separately';
 ASSERT (SELECT count(*)=1 FROM analytics.v_evento_comercial_actual WHERE tipo_evento='MINUTA' AND codigo_unidad='B'),'cancelled documentary sale preserved';
 ASSERT (SELECT disponible=false AND estado='BLOQUEADO' FROM analytics.snapshot_unidad_diario WHERE codigo_unidad='D'),'no disponible is not available';
 ASSERT (SELECT disponible=false AND estado='VENDIDO' FROM analytics.snapshot_unidad_diario WHERE codigo_unidad='A'),'canonical sold';
 ASSERT (SELECT count(*)>0 FROM features.dataset_unidad_prediccion WHERE evidencia='RECONSTRUIDO' AND fecha_corte<'2024-01-01'),'full historical panel';
 ASSERT (SELECT bool_and(disponible IS NULL) FROM features.dataset_unidad_prediccion WHERE evidencia='RECONSTRUIDO'),'unknown historical availability stays null';
 ASSERT (SELECT bool_and(minutas_brutas IS NULL AND venta_vigente IS NULL) FROM features.unidad_prediccion_resultado WHERE NOT maduro),'right censoring';
 ASSERT (SELECT minutas_brutas=1 FROM features.unidad_prediccion_resultado WHERE codigo_unidad='A' AND fecha_corte='2023-01-31' AND horizonte_dias=30),'future target';
 ASSERT (SELECT count(*)=0 FROM features.v_dataset_unidad_entrenamiento WHERE evidencia='RECONSTRUIDO' AND elegible_validacion_prospectiva),'historical reconstruction not prospective evidence';
 ASSERT (SELECT bool_and(features->'demanda_4_semanas'->>'visitas' IS NULL) FROM features.dataset_unidad_prediccion WHERE evidencia='OBSERVADO'),'missing visits not zero';
 SELECT count(*) INTO n FROM analytics.fact_evento_comercial;
 PERFORM analytics.capture_econometric_events();
 ASSERT (SELECT count(*)=n FROM analytics.fact_evento_comercial),'idempotent unchanged events';
 SELECT count(*) INTO n FROM features.unidad_resultado_version;
 PERFORM analytics.build_econometric_datasets(true);
 ASSERT (SELECT count(*)=n FROM features.unidad_resultado_version),'unchanged outcomes do not create versions';
 BEGIN
 UPDATE analytics.snapshot_unidad_diario SET precio_lista=1 WHERE codigo_unidad='C';
 RAISE EXCEPTION 'TEST: mutation should fail';
 EXCEPTION WHEN raise_exception THEN
 IF SQLERRM='TEST: mutation should fail' THEN RAISE; END IF;
 END;
 BEGIN
 UPDATE features.dataset_unidad_prediccion SET features='{}' WHERE evidencia='OBSERVADO';
 RAISE EXCEPTION 'TEST: mutation should fail';
 EXCEPTION WHEN raise_exception THEN
 IF SQLERRM='TEST: mutation should fail' THEN RAISE; END IF;
 END;
END $$;
UPDATE analytics.v_absorcion_ventas_ciclos SET fecha_venta_documental='2023-02-15' WHERE codigo_unidad='A';
SELECT analytics.capture_econometric_events();
DO $$ BEGIN
 ASSERT (SELECT count(*)=2 FROM analytics.fact_evento_comercial WHERE event_key='CICLO|A|PA|MINUTA'),'correction preserves original';
 ASSERT (SELECT fecha_evento='2023-02-15' FROM analytics.v_evento_comercial_actual WHERE event_key='CICLO|A|PA|MINUTA'),'latest version selected';
END $$;
DELETE FROM analytics.v_absorcion_ventas_ciclos WHERE codigo_unidad='A';
SELECT analytics.capture_econometric_events();
SELECT analytics.build_econometric_datasets(true);
DO $$ BEGIN
 ASSERT (SELECT activo=false FROM analytics.v_evento_comercial_actual WHERE event_key='CICLO|A|PA|MINUTA'),'source removal tombstone';
 ASSERT (SELECT count(*)=3 FROM analytics.fact_evento_comercial WHERE event_key='CICLO|A|PA|MINUTA'),'full event audit';
 ASSERT (SELECT count(*)=2 FROM features.unidad_resultado_version WHERE codigo_unidad='A' AND fecha_corte='2023-01-31' AND horizonte_dias=30),'revised labels audited';
END $$;
INSERT INTO model_control.prediccion_unidad(prediction_id,modelo,version_modelo,codigo_unidad,fecha_corte,evidencia,horizonte_dias,objetivo,probabilidad)
SELECT 'TEST1','baseline','1','C',(CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date,'OBSERVADO',30,'MINUTA_BRUTA_AL_MENOS_UNA',0.3;
DO $$ BEGIN
 ASSERT (SELECT resultado IS NULL AND brier IS NULL AND emitido_antes_ventana FROM analytics.v_prediccion_unidad_evaluacion WHERE prediction_id='TEST1'),'issued before unknown outcome';
 BEGIN
 INSERT INTO model_control.prediccion_unidad(prediction_id,modelo,version_modelo,codigo_unidad,fecha_corte,evidencia,horizonte_dias,objetivo,probabilidad)
 VALUES('OLD','baseline','1','C','2024-01-01','OBSERVADO',30,'MINUTA_BRUTA_AL_MENOS_UNA',0.3);
 RAISE EXCEPTION 'TEST: historical prediction should fail';
 EXCEPTION WHEN raise_exception THEN
 IF SQLERRM='TEST: historical prediction should fail' THEN RAISE; END IF;
 END;
END $$;
INSERT INTO analytics.proyecto_mercado_econometria VALUES('Q','LIMA');
INSERT INTO analytics.contexto_mercado_mes(mercado,indicador,periodo_mes,publicado_at,valor,unidad,fuente,ingested_at)
SELECT 'LIMA','TASA',date_trunc('month',CURRENT_TIMESTAMP)::date,CURRENT_TIMESTAMP+interval '1 day',5,'pct','TEST',CURRENT_TIMESTAMP;
DO $$ BEGIN
 ASSERT (SELECT count(*)=0 FROM features.v_contexto_mercado_por_corte WHERE evidencia='OBSERVADO'),'no future publications';
END $$;
DO $$ BEGIN
 ASSERT (SELECT count(*)=3 FROM analytics.v_econometria_serie_precios),'separate currency/project baskets';
 ASSERT (SELECT bool_and(abs(indice_base_100-100)<0.00001) FROM analytics.v_econometria_serie_precios),'normalized first basket';
 ASSERT (SELECT count(*)>0 FROM features.v_estacionalidad_panel WHERE periodo_mes<'2024-01-01'),'seasonality before 2024';
END $$;
INSERT INTO analytics.historial_oferta_unidad(codigo_unidad,codigo_proyecto,tipo_precio,fecha_referencia,disponible_desde,precio,moneda,area_total,fuente,clave_fuente,calidad)
SELECT 'C','Q','LISTA',CURRENT_DATE,CURRENT_TIMESTAMP+interval '1 hour',1,'USD',40,'TEST','BAD','IMPORTADO_DOCUMENTAL_PENDIENTE_AUDITORIA';
DO $$ BEGIN
 ASSERT (SELECT abs(indice_base_100-100)<0.00001 FROM analytics.v_econometria_serie_precios WHERE codigo_proyecto='Q'),'unverified imports excluded from observed index';
END $$;
