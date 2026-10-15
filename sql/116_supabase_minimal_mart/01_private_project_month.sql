-- MEDALLIO pilot: small, private analytical source for a next-month sales baseline.
-- Source of truth stays in local analytics.comercial_proyecto_mes.
CREATE SCHEMA IF NOT EXISTS medallio_pilot;
REVOKE ALL ON SCHEMA medallio_pilot FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE IF NOT EXISTS medallio_pilot.project_month (
    project_ref text NOT NULL CHECK (project_ref ~ '^[0-9a-f]{64}$'),
    period_month date NOT NULL CHECK (period_month = date_trunc('month', period_month)::date),
    life_month integer NOT NULL CHECK (life_month > 0),
    calendar_month smallint NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    source_cutoff date NOT NULL CHECK (source_cutoff >= period_month),
    is_partial boolean NOT NULL,
    stock_open bigint NOT NULL CHECK (stock_open >= 0),
    sales_units bigint NOT NULL CHECK (sales_units >= 0),
    stock_close bigint NOT NULL CHECK (stock_close >= 0),
    exposure_days bigint NOT NULL CHECK (exposure_days >= 0),
    review_units bigint NOT NULL CHECK (review_units >= 0),
    source_hash text NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    data_origin text NOT NULL CHECK (data_origin IN ('MEDALLIO_AGGREGATE', 'SYNTHETIC')),
    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_ref, period_month),
    CHECK (stock_open - sales_units = stock_close),
    CHECK (calendar_month = extract(month FROM period_month))
);

-- Defense in depth even though the schema is not exposed to the Data API.
ALTER TABLE medallio_pilot.project_month ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON medallio_pilot.project_month FROM PUBLIC, anon, authenticated, service_role;
CREATE INDEX IF NOT EXISTS project_month_period_idx
    ON medallio_pilot.project_month (period_month);

CREATE OR REPLACE VIEW medallio_pilot.v_next_month_training
WITH (security_invoker = true) AS
SELECT
    x.project_ref,
    x.period_month AS feature_month,
    y.period_month AS target_month,
    x.life_month,
    x.calendar_month,
    x.stock_close AS stock_before_target,
    x.sales_units AS sales_previous_month,
    x.exposure_days AS exposure_previous_month,
    y.sales_units AS target_sales_units,
    x.data_origin,
    'RETROSPECTIVE_REVISED_NOT_AS_ISSUED'::text AS evidence_level
FROM medallio_pilot.project_month AS x
JOIN medallio_pilot.project_month AS y
  ON y.project_ref = x.project_ref
 AND y.period_month = (x.period_month + interval '1 month')::date
 AND y.data_origin = x.data_origin
WHERE NOT x.is_partial AND NOT y.is_partial
  AND x.review_units = 0 AND y.review_units = 0;

REVOKE ALL ON medallio_pilot.v_next_month_training FROM PUBLIC, anon, authenticated, service_role;

COMMENT ON TABLE medallio_pilot.project_month IS
'Project-month aggregates only; opaque HMAC project reference; no CRM row data or names.';
COMMENT ON VIEW medallio_pilot.v_next_month_training IS
'Retrospective month-to-next-month training pairs. Not prospective forecast evidence.';
