-- Unit semantics / absorption v1.1
-- Certified current-stock snapshot.
--
-- Why this layer exists:
-- fact_movimientos_stock is an event ledger and remains authoritative for
-- observed commercial transitions. Its ALTA_STOCK currently starts at the
-- first observable proforma_unidad event, so units that have never been
-- proformed can be absent from the historical ledger even though they exist
-- in core.dim_unidad and are currently available.
--
-- We therefore do NOT invent a historical entry date. Instead:
--   * current stock is certified from the current unit dimension;
--   * event history remains in the ledger;
--   * coverage between both worlds is explicit;
--   * daily snapshots start accumulating point-in-time evidence from now on.

CREATE TABLE IF NOT EXISTS analytics.fact_stock_snapshot_diario_unidad (
    fecha_snapshot date NOT NULL,
    codigo_unidad text NOT NULL,
    codigo_proyecto text,
    tipo_unidad_consolidado text NOT NULL,

    estado_comercial_consolidado text NOT NULL,
    orden_estado integer NOT NULL,

    flag_departamento boolean NOT NULL,
    flag_estacionamiento boolean NOT NULL,
    flag_deposito boolean NOT NULL,
    flag_local boolean NOT NULL,
    flag_otro_tipo boolean NOT NULL,

    flag_disponible boolean NOT NULL,
    flag_bloqueado boolean NOT NULL,
    flag_estado_separado boolean NOT NULL,
    flag_vendido boolean NOT NULL,
    flag_otro_estado boolean NOT NULL,

    captured_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(fecha_snapshot,codigo_unidad)
);

CREATE INDEX IF NOT EXISTS ix_stock_snapshot_fecha_proyecto_tipo
    ON analytics.fact_stock_snapshot_diario_unidad(
        fecha_snapshot,codigo_proyecto,tipo_unidad_consolidado
    );

CREATE INDEX IF NOT EXISTS ix_stock_snapshot_estado
    ON analytics.fact_stock_snapshot_diario_unidad(
        fecha_snapshot,estado_comercial_consolidado,orden_estado
    );

CREATE OR REPLACE PROCEDURE analytics.refresh_stock_snapshot_actual_v11()
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM analytics.fact_stock_snapshot_diario_unidad
    WHERE fecha_snapshot=current_date;

    INSERT INTO analytics.fact_stock_snapshot_diario_unidad(
        fecha_snapshot,codigo_unidad,codigo_proyecto,tipo_unidad_consolidado,
        estado_comercial_consolidado,orden_estado,
        flag_departamento,flag_estacionamiento,flag_deposito,flag_local,flag_otro_tipo,
        flag_disponible,flag_bloqueado,flag_estado_separado,flag_vendido,flag_otro_estado
    )
    SELECT
        current_date,
        codigo_unidad,
        codigo_proyecto,
        tipo_unidad_consolidado,
        estado_comercial_consolidado,
        orden_estado,
        flag_departamento,
        flag_estacionamiento,
        flag_deposito,
        flag_local,
        flag_otro_tipo,
        flag_disponible,
        flag_bloqueado,
        flag_estado_separado,
        flag_vendido,
        flag_otro_estado
    FROM analytics.dim_unidad_semantica;
END $$;

-- Preserve the old event-ledger current view under an explicit name.
CREATE OR REPLACE VIEW analytics.v_stock_ledger_actual_por_tipo AS
SELECT DISTINCT ON (codigo_proyecto,tipo_unidad_consolidado)
    codigo_proyecto,
    tipo_unidad_consolidado,
    fecha,
    stock_fin,
    separadas_activas,
    vendidas_acumuladas
FROM analytics.fact_stock_ofertado_diario_tipo
ORDER BY codigo_proyecto,tipo_unidad_consolidado,fecha DESC;

-- Current stock is now a complete current-state snapshot, not an event-ledger
-- proxy. Existing columns are preserved for downstream compatibility.
CREATE OR REPLACE VIEW analytics.v_stock_consolidado_actual_por_tipo AS
WITH latest AS (
    SELECT max(fecha_snapshot) AS fecha
    FROM analytics.fact_stock_snapshot_diario_unidad
)
SELECT
    s.codigo_proyecto,
    s.tipo_unidad_consolidado,
    s.fecha_snapshot AS fecha,
    count(*) FILTER (WHERE s.flag_disponible)::bigint AS stock_fin,
    count(*) FILTER (WHERE s.flag_estado_separado)::bigint AS separadas_activas,
    count(*) FILTER (WHERE s.flag_vendido)::bigint AS vendidas_acumuladas,
    count(*) FILTER (WHERE s.flag_bloqueado)::bigint AS bloqueadas_actuales,
    count(*) FILTER (WHERE s.flag_otro_estado)::bigint AS otros_estados,
    count(*)::bigint AS unidades_total,
    'SNAPSHOT_DIM_UNIDAD'::text AS fuente_stock
FROM analytics.fact_stock_snapshot_diario_unidad s
JOIN latest l ON l.fecha=s.fecha_snapshot
GROUP BY s.codigo_proyecto,s.tipo_unidad_consolidado,s.fecha_snapshot;

-- Explicit reconciliation between complete current stock and observed ledger.
CREATE OR REPLACE VIEW analytics.v_stock_coverage_actual_por_tipo AS
WITH current_stock AS (
    SELECT
        codigo_proyecto,
        tipo_unidad_consolidado,
        fecha,
        stock_fin,
        separadas_activas,
        vendidas_acumuladas,
        bloqueadas_actuales,
        otros_estados,
        unidades_total
    FROM analytics.v_stock_consolidado_actual_por_tipo
), ledger AS (
    SELECT *
    FROM analytics.v_stock_ledger_actual_por_tipo
)
SELECT
    coalesce(c.codigo_proyecto,l.codigo_proyecto) AS codigo_proyecto,
    coalesce(c.tipo_unidad_consolidado,l.tipo_unidad_consolidado) AS tipo_unidad_consolidado,
    c.fecha AS fecha_snapshot,
    l.fecha AS fecha_ledger,

    coalesce(c.stock_fin,0) AS stock_disponible_actual,
    coalesce(l.stock_fin,0) AS stock_disponible_ledger,
    coalesce(c.stock_fin,0)-coalesce(l.stock_fin,0) AS gap_stock_disponible,

    coalesce(c.separadas_activas,0) AS separadas_actual,
    coalesce(l.separadas_activas,0) AS separadas_ledger,
    coalesce(c.separadas_activas,0)-coalesce(l.separadas_activas,0) AS gap_separadas,

    coalesce(c.vendidas_acumuladas,0) AS vendidas_actual,
    coalesce(l.vendidas_acumuladas,0) AS vendidas_ledger,
    coalesce(c.vendidas_acumuladas,0)-coalesce(l.vendidas_acumuladas,0) AS gap_vendidas,

    coalesce(c.bloqueadas_actuales,0) AS bloqueadas_actuales,
    coalesce(c.otros_estados,0) AS otros_estados,
    coalesce(c.unidades_total,0) AS unidades_total_actual,

    CASE
        WHEN coalesce(c.stock_fin,0)=0 AND coalesce(l.stock_fin,0)=0 THEN 1::numeric
        ELSE coalesce(l.stock_fin,0)::numeric/nullif(coalesce(c.stock_fin,0),0)
    END AS cobertura_stock_disponible_ratio,

    (
        coalesce(c.stock_fin,0)=coalesce(l.stock_fin,0)
        AND coalesce(c.separadas_activas,0)=coalesce(l.separadas_activas,0)
        AND coalesce(c.vendidas_acumuladas,0)=coalesce(l.vendidas_acumuladas,0)
    ) AS ledger_reconcilia_estado_actual
FROM current_stock c
FULL OUTER JOIN ledger l
  ON l.codigo_proyecto=c.codigo_proyecto
 AND l.tipo_unidad_consolidado=c.tipo_unidad_consolidado;

-- Latest principal (department) absorption accompanied by its current stock
-- coverage status. Absorption values remain observed-ledger metrics; this view
-- prevents consumers from mistaking them for fully certified stock history.
CREATE OR REPLACE VIEW analytics.v_absorcion_principal_estado_actual AS
WITH latest_abs AS (
    SELECT DISTINCT ON (codigo_proyecto)
        *
    FROM analytics.v_absorcion_principal_proyecto_diario
    ORDER BY codigo_proyecto,fecha DESC
)
SELECT
    a.*,
    c.stock_disponible_actual,
    c.stock_disponible_ledger,
    c.gap_stock_disponible,
    c.cobertura_stock_disponible_ratio,
    c.ledger_reconcilia_estado_actual,
    CASE
        WHEN c.ledger_reconcilia_estado_actual THEN 'CERTIFICADO_ESTADO_ACTUAL'
        ELSE 'HISTORICO_LEDGER_CON_GAP_DE_COBERTURA'
    END AS calidad_stock
FROM latest_abs a
LEFT JOIN analytics.v_stock_coverage_actual_por_tipo c
  ON c.codigo_proyecto=a.codigo_proyecto
 AND c.tipo_unidad_consolidado='DEPARTAMENTO';

-- Metric contract v1.1. The word OBSERVADA is intentional until a sufficient
-- run of certified snapshots exists to replace/improve historical denominators.
INSERT INTO analytics.metric_definitions(
    metric_name,business_definition,numerator_definition,
    denominator_definition,version,valid_from,is_active
)
VALUES
(
    'absorcion_bruta_departamentos_30d_observada',
    'Separaciones físicas efectivas de departamentos en 30 días divididas entre stock de departamentos observado por el ledger al inicio de la ventana. No mezcla accesorios.',
    'separaciones_brutas_30d where tipo_unidad_consolidado=DEPARTAMENTO',
    'stock_inicio_ventana_30d observado por ledger',
    '1.1',
    DATE '2026-08-28',
    true
),
(
    'absorcion_neta_departamentos_30d_observada',
    'Separaciones físicas efectivas menos caídas efectivas de departamentos en 30 días, dividido entre stock de departamentos observado por el ledger al inicio de la ventana. No mezcla accesorios.',
    'separaciones_netas_30d where tipo_unidad_consolidado=DEPARTAMENTO',
    'stock_inicio_ventana_30d observado por ledger',
    '1.1',
    DATE '2026-08-28',
    true
),
(
    'stock_disponible_actual_departamentos',
    'Departamentos actualmente disponibles según snapshot certificado de la dimensión de unidad.',
    'count(*) where flag_departamento and flag_disponible',
    NULL,
    '1.1',
    DATE '2026-08-28',
    true
)
ON CONFLICT (metric_name) DO UPDATE
SET
    business_definition=EXCLUDED.business_definition,
    numerator_definition=EXCLUDED.numerator_definition,
    denominator_definition=EXCLUDED.denominator_definition,
    version=EXCLUDED.version,
    valid_from=EXCLUDED.valid_from,
    is_active=true;
