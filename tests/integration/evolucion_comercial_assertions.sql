SELECT analytics.refresh_evolucion_comercial();
DO $$ BEGIN
 ASSERT (SELECT count(*)=3 FROM analytics.comercial_proyecto_mes WHERE codigo_proyecto='P'), 'stop at sellout, include pre-2024';
 ASSERT (SELECT stock_inicial=2 AND ventas_mes=0 AND stock_final=2 AND mes_vida=1 FROM analytics.comercial_proyecto_mes WHERE codigo_proyecto='P' AND periodo_mes='2023-01-01'), 'launch and zero sales';
 ASSERT (SELECT stock_inicial=2 AND ventas_mes=1 AND stock_final=1 AND dias_exposicion=38 FROM analytics.comercial_proyecto_mes WHERE codigo_proyecto='P' AND periodo_mes='2023-02-01'), 'balance and exposure';
 ASSERT (SELECT dias_exposicion=0 FROM analytics.comercial_unidad_mes WHERE codigo_unidad='A' AND periodo_mes='2023-03-01'), 'sold unit exposure';
 ASSERT (SELECT count(*)=0 FROM analytics.comercial_unidad_mes WHERE precio_m2 IS NOT NULL), 'no lookahead from current price';
 ASSERT (SELECT abs(area_relativa-2.0/3)<0.00001 FROM analytics.comercial_unidad_mes WHERE codigo_unidad='A' AND periodo_mes='2023-01-01'), 'area ratio';
 ASSERT (SELECT max(periodo_mes)=date_trunc('month',CURRENT_TIMESTAMP AT TIME ZONE 'America/Lima')::date FROM analytics.comercial_proyecto_mes WHERE codigo_proyecto='Q'), 'unsold to current month';
 ASSERT (SELECT bool_and(unidades_revision=1) FROM analytics.comercial_proyecto_mes WHERE codigo_proyecto='Q'), 'quality visible';
 ASSERT (SELECT count(*)=4 FROM analytics.comercial_precio_observado), 'daily observations';
END $$;
UPDATE core.dim_unidad SET precio_lista_actual=999999 WHERE codigo_unidad='A';
SELECT analytics.refresh_evolucion_comercial();
DO $$ BEGIN
 ASSERT (SELECT count(*)=4 FROM analytics.comercial_precio_observado), 'idempotence';
 ASSERT (SELECT precio_lista=200000 FROM analytics.comercial_precio_observado WHERE codigo_unidad='A'), 'first observation immutable';
END $$;
INSERT INTO analytics.comercial_precio_observado(fecha_observacion,codigo_unidad,codigo_proyecto,area_total,moneda,precio_lista) VALUES
 ('2023-01-31','A','P',50,'PEN',100000),('2023-01-31','B','P',100,'PEN',200000),
 ('2023-02-28','A','P',50,'PEN',110000),('2023-02-28','B','P',100,'PEN',220000),
 ('2023-03-31','A','P',50,'PEN',120000);
SELECT analytics.refresh_evolucion_comercial();
DO $$ BEGIN
 ASSERT (SELECT abs(indice_base_100-100)<0.00001 FROM analytics.v_comercial_indice_precios WHERE codigo_proyecto='P' AND periodo_mes='2023-01-01'), 'base 100';
 ASSERT (SELECT abs(indice_base_100-110)<0.00001 FROM analytics.v_comercial_indice_precios WHERE codigo_proyecto='P' AND periodo_mes='2023-02-01'), 'fixed basket +10 percent';
 ASSERT (SELECT indice_base_100 IS NULL AND cobertura=0.5 FROM analytics.v_comercial_indice_precios WHERE codigo_proyecto='P' AND periodo_mes='2023-03-01'), 'missing basket not silently rebased';
 ASSERT (SELECT precio_m2=2000 AND precio_relativo=1 FROM analytics.comercial_unidad_mes WHERE codigo_unidad='A' AND periodo_mes='2023-02-01'), 'lagged relative price';
 ASSERT (SELECT count(*)=0 FROM analytics.comercial_unidad_mes WHERE stock_inicial-venta_mes<>stock_final), 'all balances';
END $$;
