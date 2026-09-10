-- Pricing Projection Mart v1
-- Controlled assumptions migrated from Power BI M into Medallio.
-- These are scenario inputs, NOT observed stock facts and NOT causal forecasts.

CREATE SCHEMA IF NOT EXISTS pricing;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS pricing.projection_baseline_assumption (
    proyecto                 text NOT NULL,
    tipo_unidad              text NOT NULL,
    nombre_tipologia         text NOT NULL,
    tipologia_ubicacion      integer NOT NULL,
    stock_total_inicial      numeric NOT NULL CHECK (stock_total_inicial >= 0),
    precio_m2_base           numeric NOT NULL CHECK (precio_m2_base >= 0),
    area_total_promedio      numeric NOT NULL CHECK (area_total_promedio > 0),
    descuento_promedio       numeric NOT NULL CHECK (descuento_promedio >= 0 AND descuento_promedio < 1),
    ventas_mes_base          numeric NOT NULL CHECK (ventas_mes_base >= 0),
    meta_meses               integer NOT NULL CHECK (meta_meses > 0),
    fecha_inicio             date NOT NULL DEFAULT DATE '2026-01-01',
    activo                   boolean NOT NULL DEFAULT true,
    origen_supuesto          text NOT NULL DEFAULT 'POWER_BI_MANUAL_V1',
    updated_at               timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (proyecto, tipo_unidad, nombre_tipologia, tipologia_ubicacion)
);

CREATE TABLE IF NOT EXISTS pricing.absorption_scenario (
    escenario                text NOT NULL,
    tramo                    integer NOT NULL CHECK (tramo > 0),
    mes_inicio               integer NOT NULL CHECK (mes_inicio > 0),
    mes_fin                  integer NOT NULL CHECK (mes_fin >= mes_inicio),
    factor_ventas            numeric NOT NULL CHECK (factor_ventas >= 0),
    activo                   boolean NOT NULL DEFAULT true,
    origen_supuesto          text NOT NULL DEFAULT 'POWER_BI_MANUAL_V1',
    updated_at               timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (escenario, tramo)
);

CREATE TABLE IF NOT EXISTS pricing.price_milestone (
    proyecto                 text NOT NULL,
    tipo_unidad              text NOT NULL,
    nombre_tipologia         text NOT NULL,
    hito                     integer NOT NULL CHECK (hito > 0),
    mes_hito                 integer NOT NULL CHECK (mes_hito > 0),
    pct_vendido_objetivo     numeric NOT NULL CHECK (pct_vendido_objetivo >= 0 AND pct_vendido_objetivo <= 1),
    aumento_usd_m2           numeric NOT NULL,
    activo                   boolean NOT NULL DEFAULT true,
    origen_supuesto          text NOT NULL DEFAULT 'POWER_BI_MANUAL_V1',
    updated_at               timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (proyecto, tipo_unidad, nombre_tipologia, hito)
);

COMMENT ON TABLE pricing.projection_baseline_assumption IS
'Inputs manuales/versionables del simulador de pricing. stock_total_inicial es baseline de escenario, no stock observado actual.';
COMMENT ON TABLE pricing.absorption_scenario IS
'Curvas por tramos que multiplican ventas_mes_base por escenario y mes.';
COMMENT ON TABLE pricing.price_milestone IS
'Hitos de pricing: se activan por mes_hito OR pct_vendido_objetivo, preservando la semántica del M original.';
COMMENT ON COLUMN pricing.price_milestone.aumento_usd_m2 IS
'Nombre heredado del modelo Power BI. Se preserva numéricamente; validar moneda/unidad antes de decisiones reales.';

-- Seed activo actual de Base_Proyeccion_Tipologia.
-- Los bloques comentados/legacy del M NO se activan silenciosamente.
INSERT INTO pricing.projection_baseline_assumption (
    proyecto, tipo_unidad, nombre_tipologia, tipologia_ubicacion,
    stock_total_inicial, precio_m2_base, area_total_promedio,
    descuento_promedio, ventas_mes_base, meta_meses, fecha_inicio
)
VALUES
    ('Torre Marsano','departamento flat','M1', 1,23,5800,58,0.05,0.8,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M2', 2,15,6627,72,0.04,1.4,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M3', 3,21,5900,60,0.05,0.9,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M4', 4,18,6338,75,0.04,1.1,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M5', 5,23,5850,59,0.05,0.8,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M6', 6,17,6050,68,0.04,1.2,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M7', 7,20,5950,64,0.05,1.0,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M8', 8,19,6100,70,0.04,1.0,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M9', 9,17,6659,78,0.03,1.2,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M10',10,17,6246,74,0.04,1.2,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M11',11,14,6150,76,0.04,1.4,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M12',12,21,6324,77,0.03,0.9,24,DATE '2026-01-01'),
    ('Torre Marsano','departamento flat','M13',13,11,5515,67,0.05,1.6,24,DATE '2026-01-01')
ON CONFLICT DO NOTHING;

INSERT INTO pricing.absorption_scenario (
    escenario, tramo, mes_inicio, mes_fin, factor_ventas
)
VALUES
    ('Conservador',1, 1, 6,0.70),
    ('Conservador',2, 7,12,0.85),
    ('Conservador',3,13,18,0.95),
    ('Conservador',4,19,24,0.85),
    ('Conservador',5,25,30,0.70),
    ('Base',1, 1, 6,0.80),
    ('Base',2, 7,12,1.00),
    ('Base',3,13,18,1.10),
    ('Base',4,19,24,0.90),
    ('Base',5,25,30,0.75),
    ('Agresivo',1, 1, 6,0.90),
    ('Agresivo',2, 7,12,1.10),
    ('Agresivo',3,13,18,1.20),
    ('Agresivo',4,19,24,1.00),
    ('Agresivo',5,25,30,0.85)
ON CONFLICT DO NOTHING;

INSERT INTO pricing.price_milestone (
    proyecto, tipo_unidad, nombre_tipologia, hito,
    mes_hito, pct_vendido_objetivo, aumento_usd_m2
)
VALUES
    ('Torre Nápoles','departamento flat','Tipología 2',1, 6,0.25,35),
    ('Torre Nápoles','departamento flat','Tipología 2',2,12,0.45,40),
    ('Torre Nápoles','departamento flat','Tipología 2',3,18,0.65,50),
    ('Torre Nápoles','departamento flat','Tipología 2',4,24,0.85,60),

    ('Torre Marsano','departamento flat','M1',1, 6,0.25,0),
    ('Torre Marsano','departamento flat','M1',2,12,0.45,0),
    ('Torre Marsano','departamento flat','M1',3,18,0.65,0),
    ('Torre Marsano','departamento flat','M2',1, 6,0.25,35),
    ('Torre Marsano','departamento flat','M2',2,12,0.45,45),
    ('Torre Marsano','departamento flat','M2',3,18,0.65,55),
    ('Torre Marsano','departamento flat','M3',1, 6,0.25,0),
    ('Torre Marsano','departamento flat','M3',2,12,0.45,0),
    ('Torre Marsano','departamento flat','M3',3,18,0.65,0),
    ('Torre Marsano','departamento flat','M4',1, 6,0.25,30),
    ('Torre Marsano','departamento flat','M4',2,12,0.45,35),
    ('Torre Marsano','departamento flat','M4',3,18,0.65,40),
    ('Torre Marsano','departamento flat','M5',1, 6,0.25,0),
    ('Torre Marsano','departamento flat','M5',2,12,0.45,0),
    ('Torre Marsano','departamento flat','M5',3,18,0.65,0),
    ('Torre Marsano','departamento flat','M6',1, 6,0.25,35),
    ('Torre Marsano','departamento flat','M6',2,12,0.45,45),
    ('Torre Marsano','departamento flat','M6',3,18,0.65,55),
    ('Torre Marsano','departamento flat','M7',1, 6,0.25,0),
    ('Torre Marsano','departamento flat','M7',2,12,0.45,0),
    ('Torre Marsano','departamento flat','M7',3,18,0.65,0),
    ('Torre Marsano','departamento flat','M8',1, 6,0.25,20),
    ('Torre Marsano','departamento flat','M8',2,12,0.45,25),
    ('Torre Marsano','departamento flat','M8',3,18,0.65,30),
    ('Torre Marsano','departamento flat','M9',1, 6,0.25,20),
    ('Torre Marsano','departamento flat','M9',2,12,0.45,25),
    ('Torre Marsano','departamento flat','M9',3,18,0.65,30),
    ('Torre Marsano','departamento flat','M10',1, 6,0.25,20),
    ('Torre Marsano','departamento flat','M10',2,12,0.45,25),
    ('Torre Marsano','departamento flat','M10',3,18,0.65,30),
    ('Torre Marsano','departamento flat','M11',1, 6,0.25,35),
    ('Torre Marsano','departamento flat','M11',2,12,0.45,45),
    ('Torre Marsano','departamento flat','M11',3,18,0.65,55),
    ('Torre Marsano','departamento flat','M12',1, 6,0.25,0),
    ('Torre Marsano','departamento flat','M12',2,12,0.45,0),
    ('Torre Marsano','departamento flat','M12',3,18,0.65,0),
    ('Torre Marsano','departamento flat','M13',1, 6,0.20,40),
    ('Torre Marsano','departamento flat','M13',2,12,0.40,55),
    ('Torre Marsano','departamento flat','M13',3,18,0.60,70)
ON CONFLICT DO NOTHING;
