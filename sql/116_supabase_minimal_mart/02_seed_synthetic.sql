-- Optional synthetic smoke test. Never substitute these values for MEDALLIO data.
WITH demo AS (
    SELECT p.project_ref, p.base_stock, m.period_month::date,
           row_number() OVER (PARTITION BY p.project_ref ORDER BY m.period_month)::int AS life_month,
           (2 + (extract(month FROM m.period_month)::int % 3) + p.sales_offset)::bigint AS sales_units
    FROM (VALUES (repeat('a',64), 80::bigint, 0::bigint),
                 (repeat('b',64), 60::bigint, 1::bigint)) AS p(project_ref, base_stock, sales_offset)
    CROSS JOIN generate_series(date '2025-01-01', date '2025-12-01', interval '1 month') AS m(period_month)
), balances AS (
    SELECT *, base_stock - coalesce(
        sum(sales_units) OVER (PARTITION BY project_ref ORDER BY period_month
                              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0
    ) AS stock_open
    FROM demo
)
INSERT INTO medallio_pilot.project_month (
    project_ref, period_month, life_month, calendar_month, source_cutoff,
    is_partial, stock_open, sales_units, stock_close, exposure_days,
    review_units, source_hash, data_origin
)
SELECT project_ref, period_month, life_month, extract(month FROM period_month)::int,
       date '2025-12-31', false, stock_open, sales_units, stock_open-sales_units,
       stock_open*28, 0,
       md5(project_ref || period_month::text || sales_units::text) ||
       md5('synthetic:' || project_ref || period_month::text),
       'SYNTHETIC'
FROM balances
ON CONFLICT (project_ref, period_month) DO NOTHING;
