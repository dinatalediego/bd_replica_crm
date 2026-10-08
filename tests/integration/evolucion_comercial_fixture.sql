CREATE SCHEMA analytics;
CREATE SCHEMA core;
CREATE TABLE core.dim_unidad(codigo_unidad text PRIMARY KEY,nombre_tipologia text,
 total_habitaciones numeric,area_total numeric,moneda_precio_lista text,
 precio_lista_actual numeric,source_loaded_at timestamptz);
CREATE TABLE analytics.v_absorcion_ventas_unidad(codigo_unidad text PRIMARY KEY,
 codigo_proyecto text,nombre_proyecto text,fecha_ingreso_stock date,fecha_venta date,
 requiere_revision boolean);
INSERT INTO core.dim_unidad VALUES
 ('A','T1',2,50,'PEN',200000,now()),('B','T2',2,100,'PEN',500000,now()),
 ('C','T1',1,40,'USD',100000,now()),('D','T1',1,50,'PEN',100000,now());
INSERT INTO analytics.v_absorcion_ventas_unidad VALUES
 ('A','P','Proyecto P','2023-01-01','2023-02-10',false),
 ('B','P','Proyecto P','2023-01-01','2023-03-20',false),
 ('C','Q','Proyecto Q','2024-01-01',NULL,true),
 ('D','R','Proyecto R','2024-01-01',NULL,false);
