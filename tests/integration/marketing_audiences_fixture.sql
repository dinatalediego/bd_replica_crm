CREATE SCHEMA raw_cygnus;
CREATE SCHEMA staging;

CREATE TABLE raw_cygnus.clientes (
    id text PRIMARY KEY,
    fecha_creacion date NOT NULL
);

CREATE TABLE raw_cygnus.clientes_proyectos (
    id text PRIMARY KEY,
    cliente_id text,
    documento_cliente text,
    codigo_proyecto text,
    fecha_creacion date,
    medio_captacion text
);

CREATE TABLE raw_cygnus.procesos (
    id text PRIMARY KEY,
    cliente_id text,
    documento_cliente text,
    fecha_inicio timestamp,
    nombre text,
    codigo_proforma text,
    codigo_proyecto text,
    nombre_proyecto text
);

CREATE TABLE raw_cygnus.proformas (
    id text PRIMARY KEY,
    cliente_id text,
    documento_cliente text,
    fecha_creacion date,
    codigo_proyecto text
);

CREATE TABLE raw_cygnus.proyectos (
    codigo text PRIMARY KEY,
    nombre text
);

CREATE TABLE staging.clientes_calidad (
    source_id text,
    source_row_hash text NOT NULL,
    nombres text,
    apellidos text,
    nombre text,
    dq_nombre_cliente text,
    dq_documento_limpio text,
    dq_celular_limpio text,
    dq_email_limpio text,
    dq_medio_captacion text,
    dq_proyecto text,
    dq_celular_ok boolean NOT NULL,
    dq_email_ok boolean NOT NULL,
    dq_contacto_valido_ok boolean NOT NULL,
    dq_score_cliente integer NOT NULL,
    refreshed_at timestamptz NOT NULL
);

INSERT INTO raw_cygnus.proyectos VALUES
('P1','Matera'),
('P2','Fenix'),
('P3','Sialia'),
('P4','Nápoles'),
('P5','Modena'),
('P6','Alicanto'),
('P9','Urbanzen');

INSERT INTO raw_cygnus.clientes VALUES
('1', current_date - 300),
('2', current_date - 300),
('3', current_date - 300),
('4', current_date - 300),
('5', current_date - 30),
('6', current_date - 300);

INSERT INTO staging.clientes_calidad VALUES
('1','h1','Ana','Uno',NULL,'Ana Uno','11111111','999111111','ana@example.com','Orgánico',NULL,true,true,true,100,now()),
('2','h2','Beto','Dos',NULL,'Beto Dos','22222222','999222222','beto@example.com','Feria',NULL,true,true,true,100,now()),
('3','h3','Carla','Tres',NULL,'Carla Tres','33333333','999333333','carla@example.com','Portal',NULL,true,true,true,100,now()),
('4','h4','Diego','Cuatro',NULL,'Diego Cuatro','44444444','999444444','diego@example.com','Orgánico',NULL,true,true,true,100,now()),
('5','h5','Elena','Cinco',NULL,'Elena Cinco','55555555','999555555','elena@example.com','Feria',NULL,true,true,true,100,now()),
('6','h6','Fabio','Seis',NULL,'Fabio Seis','66666666',NULL,NULL,'Portal',NULL,false,false,false,50,now());

INSERT INTO raw_cygnus.clientes_proyectos VALUES
('cp1','1','11111111','P1',current_date - 300,'Facebook'),
('cp2','2','22222222','P2',current_date - 300,'Tik Tok'),
('cp3','3','33333333','P3',current_date - 300,'Instagram'),
('cp4','4','44444444','P4',current_date - 300,'Facebook'),
('cp5','5','55555555','P5',current_date - 30,'Google'),
('cp6','6','66666666','P6',current_date - 300,'Meta');

INSERT INTO raw_cygnus.proformas VALUES
('p1','1','11111111',current_date - 200,'P1');

INSERT INTO raw_cygnus.procesos VALUES
('e2','2','22222222',current_date - 150,'Separación','P2','P2','Fenix'),
('e3','3','33333333',current_date - 120,'Venta','P3','P9','Urbanzen');
