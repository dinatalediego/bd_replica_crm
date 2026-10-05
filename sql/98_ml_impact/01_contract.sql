-- Versioned commercial planning snapshots from the user's aggregate workbook.
-- Scenario outputs are sensitivity estimates, never model predictions or causal effects.
CREATE SCHEMA IF NOT EXISTS decision_intelligence;

CREATE TABLE IF NOT EXISTS decision_intelligence.ml_impact_snapshot (
    snapshot_id uuid PRIMARY KEY,
    as_of_date date NOT NULL,
    source_name text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    source_note text,
    semantic_definition text NOT NULL DEFAULT
        'COLOCADO=VENDIDO+SEPARADO; STOCK_REMANENTE=DISPONIBLE+BLOQUEADO; CORTE_COMERCIAL_EXCEL',
    imported_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (as_of_date, source_sha256)
);

CREATE TABLE IF NOT EXISTS decision_intelligence.ml_impact_metric (
    snapshot_id uuid NOT NULL REFERENCES decision_intelligence.ml_impact_snapshot(snapshot_id),
    codigo_proyecto text NOT NULL REFERENCES core.dim_proyecto(codigo_proyecto),
    nombre_proyecto_fuente text NOT NULL,
    bloque text NOT NULL,
    indicador text NOT NULL,
    tipo text NOT NULL,
    valor_original text,
    valor numeric(20,8) NOT NULL,
    cantidad integer CHECK (cantidad >= 0),
    PRIMARY KEY (snapshot_id, codigo_proyecto, bloque, indicador)
);

-- A new scenario_set_id is a new version: existing scenario assumptions stay auditable.
CREATE TABLE IF NOT EXISTS decision_intelligence.ml_impact_scenario (
    scenario_set_id text NOT NULL,
    scenario_code text NOT NULL,
    scenario_name text NOT NULL,
    uplift_fraction numeric(9,6) NOT NULL CHECK (uplift_fraction BETWEEN 0 AND 1),
    stock_scope text NOT NULL CHECK (stock_scope IN ('REMANENTE_INCLUYE_BLOQUEADO', 'SOLO_DISPONIBLE')),
    interpretation text NOT NULL DEFAULT 'FRACCION_ADICIONAL_DEL_STOCK; NO_MEJORA_RELATIVA_DE_CONVERSION',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scenario_set_id, scenario_code)
);

INSERT INTO decision_intelligence.ml_impact_scenario
    (scenario_set_id,scenario_code,scenario_name,uplift_fraction,stock_scope)
VALUES
    ('EXCEL_V1','CONSERVADOR','Conservador +5%',0.05,'REMANENTE_INCLUYE_BLOQUEADO'),
    ('EXCEL_V1','BASE','Base +10%',0.10,'REMANENTE_INCLUYE_BLOQUEADO'),
    ('EXCEL_V1','AGRESIVO','Agresivo +20%',0.20,'REMANENTE_INCLUYE_BLOQUEADO'),
    ('DISPONIBLE_V1','CONSERVADOR','Conservador +5%',0.05,'SOLO_DISPONIBLE'),
    ('DISPONIBLE_V1','BASE','Base +10%',0.10,'SOLO_DISPONIBLE'),
    ('DISPONIBLE_V1','AGRESIVO','Agresivo +20%',0.20,'SOLO_DISPONIBLE')
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION decision_intelligence.ml_impact_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El registro de impacto es inmutable; crear un nuevo corte o scenario_set_id';
END;
$$;

DROP TRIGGER IF EXISTS ml_impact_snapshot_append_only ON decision_intelligence.ml_impact_snapshot;
CREATE TRIGGER ml_impact_snapshot_append_only BEFORE UPDATE OR DELETE
ON decision_intelligence.ml_impact_snapshot
FOR EACH ROW EXECUTE FUNCTION decision_intelligence.ml_impact_append_only();
DROP TRIGGER IF EXISTS ml_impact_metric_append_only ON decision_intelligence.ml_impact_metric;
CREATE TRIGGER ml_impact_metric_append_only BEFORE UPDATE OR DELETE
ON decision_intelligence.ml_impact_metric
FOR EACH ROW EXECUTE FUNCTION decision_intelligence.ml_impact_append_only();
DROP TRIGGER IF EXISTS ml_impact_scenario_append_only ON decision_intelligence.ml_impact_scenario;
CREATE TRIGGER ml_impact_scenario_append_only BEFORE UPDATE OR DELETE
ON decision_intelligence.ml_impact_scenario
FOR EACH ROW EXECUTE FUNCTION decision_intelligence.ml_impact_append_only();

CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_baseline AS
WITH pivot AS (
    SELECT m.snapshot_id, m.codigo_proyecto, max(m.nombre_proyecto_fuente) AS nombre_proyecto,
        max(m.valor) FILTER (WHERE bloque='1. Resumen comercial' AND indicador='Meta Total Departamentos') AS meta_soles,
        max(m.valor) FILTER (WHERE bloque='1. Resumen comercial' AND indicador='Valor Total Colocado') AS colocado_soles,
        max(m.valor) FILTER (WHERE bloque='1. Resumen comercial' AND indicador='Gap a Meta') AS gap_reportado_soles,
        max(m.valor) FILTER (WHERE bloque='4. Composición de ventas' AND indicador='Valor Unidades Vendidas') AS vendido_soles,
        max(m.valor) FILTER (WHERE bloque='4. Composición de ventas' AND indicador='Valor Unidades Separadas') AS separado_soles,
        max(m.valor) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Stock Disponible') AS stock_remanente_soles,
        max(m.valor) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Unidades Disponible') AS stock_disponible_soles,
        coalesce(max(m.valor) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Unidades Bloqueadas'),0) AS stock_bloqueado_soles,
        max(m.cantidad) FILTER (WHERE bloque='5. Desempeño stock' AND indicador='Stock Total') AS unidades_totales,
        max(m.cantidad) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Stock Disponible') AS unidades_remanentes,
        max(m.cantidad) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Unidades Disponible') AS unidades_disponibles,
        coalesce(max(m.cantidad) FILTER (WHERE bloque='5. Stock Por vender' AND indicador='Valor Unidades Bloqueadas'),0) AS unidades_bloqueadas
    FROM decision_intelligence.ml_impact_metric m
    GROUP BY m.snapshot_id,m.codigo_proyecto
)
SELECT p.*,s.as_of_date,s.imported_at,s.source_name,s.source_sha256,s.semantic_definition,
       greatest(p.meta_soles-p.colocado_soles,0) AS gap_matematico_soles,
       p.gap_reportado_soles-greatest(p.meta_soles-p.colocado_soles,0) AS diferencia_gap_soles,
       p.stock_remanente_soles-p.stock_disponible_soles-p.stock_bloqueado_soles AS diferencia_stock_soles,
       p.colocado_soles-p.vendido_soles-p.separado_soles AS diferencia_colocado_soles,
       p.colocado_soles/nullif(p.meta_soles,0) AS cumplimiento_actual,
       CASE WHEN abs(p.gap_reportado_soles-greatest(p.meta_soles-p.colocado_soles,0))>10
                 OR abs(p.stock_remanente_soles-p.stock_disponible_soles-p.stock_bloqueado_soles)>10
                 OR abs(p.colocado_soles-p.vendido_soles-p.separado_soles)>10
            THEN 'REVISAR' ELSE 'OK' END AS conciliacion
FROM pivot p JOIN decision_intelligence.ml_impact_snapshot s USING (snapshot_id);

CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_proyecto AS
WITH basis AS (
    SELECT b.*,c.scenario_set_id,c.scenario_code,c.scenario_name,c.uplift_fraction,c.stock_scope,c.interpretation,
           CASE WHEN c.stock_scope='SOLO_DISPONIBLE' THEN b.stock_disponible_soles
                ELSE b.stock_remanente_soles END AS base_stock_soles
    FROM decision_intelligence.v_ml_impact_baseline b
    CROSS JOIN decision_intelligence.ml_impact_scenario c
), calc AS (
    SELECT basis.*,base_stock_soles*uplift_fraction AS impacto_potencial_soles,
           least(gap_matematico_soles,base_stock_soles*uplift_fraction) AS impacto_hacia_meta_soles
    FROM basis
)
SELECT calc.*,greatest(gap_matematico_soles-impacto_hacia_meta_soles,0) AS gap_restante_soles,
       (colocado_soles+impacto_hacia_meta_soles)/nullif(meta_soles,0) AS cumplimiento_simulado,
       'SIMULACION_SIN_ATRIBUCION_ML'::text AS nivel_evidencia
FROM calc;

CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_portafolio AS
SELECT snapshot_id,as_of_date,scenario_set_id,scenario_code,scenario_name,stock_scope,uplift_fraction,
       count(*) AS proyectos,
       sum(meta_soles) AS meta_soles,sum(colocado_soles) AS colocado_soles,
       sum(stock_remanente_soles) AS stock_remanente_soles,
       sum(stock_disponible_soles) AS stock_disponible_soles,
       sum(stock_bloqueado_soles) AS stock_bloqueado_soles,
       sum(gap_reportado_soles) AS gap_reportado_soles,
       sum(gap_matematico_soles) AS gap_matematico_soles,
       greatest(sum(meta_soles)-sum(colocado_soles),0) AS gap_neto_portafolio_soles,
       sum(diferencia_gap_soles) AS diferencia_gap_soles,
       sum(impacto_potencial_soles) AS impacto_potencial_soles,
       sum(impacto_hacia_meta_soles) AS impacto_hacia_meta_soles,
       sum(gap_restante_soles) AS gap_restante_soles,
       sum(colocado_soles)/nullif(sum(meta_soles),0) AS cumplimiento_actual,
       (sum(colocado_soles)+sum(impacto_hacia_meta_soles))/nullif(sum(meta_soles),0) AS cumplimiento_simulado,
       sum(impacto_hacia_meta_soles)/nullif(sum(gap_matematico_soles),0) AS proporcion_gap_cubierto,
       count(*) FILTER (WHERE conciliacion='REVISAR') AS proyectos_revision,
       'SIMULACION_SIN_ATRIBUCION_ML'::text AS nivel_evidencia
FROM decision_intelligence.v_ml_impact_proyecto
GROUP BY snapshot_id,as_of_date,scenario_set_id,scenario_code,scenario_name,stock_scope,uplift_fraction;

CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_proyecto_actual AS
SELECT p.* FROM decision_intelligence.v_ml_impact_proyecto p
WHERE p.snapshot_id = (
    SELECT s.snapshot_id FROM decision_intelligence.ml_impact_snapshot s
    ORDER BY s.as_of_date DESC,s.imported_at DESC,s.snapshot_id DESC LIMIT 1
);

CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_portafolio_actual AS
SELECT p.* FROM decision_intelligence.v_ml_impact_portafolio p
WHERE p.snapshot_id = (
    SELECT s.snapshot_id FROM decision_intelligence.ml_impact_snapshot s
    ORDER BY s.as_of_date DESC,s.imported_at DESC,s.snapshot_id DESC LIMIT 1
);

-- Diagnostic only: sales based retrospective stock does not include current
-- separations and may incorporate corrections learned after the Excel cut.
CREATE OR REPLACE VIEW decision_intelligence.v_ml_impact_vs_absorcion AS
WITH cuts AS (
    SELECT DISTINCT as_of_date FROM decision_intelligence.ml_impact_snapshot
), history AS (
    SELECT c.as_of_date,a.codigo_proyecto,a.stock_final,a.unidades_revision
    FROM cuts c CROSS JOIN LATERAL analytics.absorcion_ventas_mensual(c.as_of_date) a
    WHERE a.periodo_mes=date_trunc('month',c.as_of_date)::date
)
SELECT b.snapshot_id,b.as_of_date,b.codigo_proyecto,b.nombre_proyecto,
       b.unidades_remanentes AS remanente_excel_vendido_mas_separado,
       h.stock_final AS stock_ventas_vigentes_retrospectivo,
       b.unidades_remanentes-h.stock_final AS diferencia_unidades_no_conciliable_directamente,
       h.unidades_revision,
       'Definiciones y temporalidad distintas; usar solo como diagnóstico, no como conciliación monetaria'::text AS advertencia
FROM decision_intelligence.v_ml_impact_baseline b
LEFT JOIN history h ON h.as_of_date=b.as_of_date AND h.codigo_proyecto=b.codigo_proyecto;

COMMENT ON VIEW decision_intelligence.v_ml_impact_proyecto IS
'Sensibilidad por proyecto de un corte importado. 5/10/20% significa fracción adicional del stock, sin inferir uplift causal ni ingreso cobrado.';
