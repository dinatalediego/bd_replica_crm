ALTER TABLE core.dim_unidad ADD COLUMN piso text,ADD COLUMN area_libre numeric,
 ADD COLUMN estado_construccion text,ADD COLUMN estado_comercial text DEFAULT 'Disponible',
 ADD COLUMN estado_personalizado text;
UPDATE core.dim_unidad SET estado_comercial='No disponible' WHERE codigo_unidad='D';
CREATE TABLE analytics.v_absorcion_ventas_ciclos (
 codigo_unidad text,codigo_proyecto text,codigo_proforma text,fecha_separacion_raw date,
 fecha_venta_documental date,fecha_anulacion date,calidad_ciclo text,metodo_fecha_venta text
);
INSERT INTO analytics.v_absorcion_ventas_ciclos VALUES
 ('A','P','PA','2023-01-05','2023-02-10',NULL,'ELEGIBLE','FECHA_DE_MINUTA'),
 ('B','P','PB','2023-01-08','2023-03-20','2023-04-01','ANULADA_RETROSPECTIVAMENTE','FECHA_DE_MINUTA');
CREATE TABLE analytics.fact_movimientos_stock (
 movement_id text PRIMARY KEY,codigo_unidad text,codigo_proforma text,tipo_evento text,
 fecha_evento date,estado_anterior text,estado_nuevo text,delta_stock integer,
 source_event_key text,transition_applied boolean
);
INSERT INTO analytics.fact_movimientos_stock VALUES ('L1','A','PA','SEPARACION','2023-01-05','AVAILABLE','SEPARATED',-1,'test',true);
