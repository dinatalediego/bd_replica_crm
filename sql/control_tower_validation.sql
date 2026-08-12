-- Ejecutar en DBeaver sobre medallio_dw después de instalar Sprint 1.

-- 1) Activos registrados y su impacto de negocio.
SELECT
    asset_key,
    enabled,
    criticality,
    business_process,
    freshness_sla_minutes,
    business_impact,
    downstream_products
FROM observability.asset_registry
ORDER BY
    CASE criticality
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END,
    asset_key;

-- 2) Estado operacional actual.
SELECT
    asset_key,
    criticality,
    health_status,
    last_run_status,
    last_success_at,
    minutes_since_success,
    replication_lag_minutes,
    operational_health_score,
    downstream_products
FROM observability.v_asset_health_current
ORDER BY
    CASE health_status
        WHEN 'FAIL' THEN 1
        WHEN 'WARN' THEN 2
        WHEN 'UNKNOWN' THEN 3
        ELSE 4
    END,
    criticality,
    asset_key;

-- 3) Últimos snapshots.
SELECT *
FROM observability.asset_snapshots
ORDER BY snapshot_at DESC
LIMIT 100;

-- 4) Checks de calidad que requieren atención.
SELECT
    checked_at,
    asset_key,
    criticality,
    quality_dimension,
    check_name,
    status,
    metric_value,
    threshold_value,
    details,
    business_impact
FROM observability.v_quality_checks
WHERE status IN ('WARN','FAIL')
ORDER BY checked_at DESC
LIMIT 100;

-- 5) Últimos runs del pipeline.
SELECT
    started_at,
    asset_key,
    status,
    rows_loaded,
    duration_minutes,
    error_message
FROM observability.v_pipeline_runs
ORDER BY started_at DESC
LIMIT 100;
