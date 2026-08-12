from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthResult:
    freshness_status: str
    replication_status: str
    pipeline_status: str
    health_status: str
    score: float


def classify_health(
    *,
    minutes_since_success: float | None,
    freshness_sla_minutes: int,
    replication_lag_minutes: float | None,
    replication_lag_sla_minutes: int,
    last_run_status: str | None,
) -> HealthResult:
    if minutes_since_success is None:
        freshness = "UNKNOWN"
    elif minutes_since_success <= freshness_sla_minutes:
        freshness = "OK"
    elif minutes_since_success <= freshness_sla_minutes * 1.5:
        freshness = "WARN"
    else:
        freshness = "FAIL"

    if replication_lag_minutes is None:
        replication = "UNKNOWN"
    elif replication_lag_minutes <= replication_lag_sla_minutes:
        replication = "OK"
    elif replication_lag_minutes <= max(replication_lag_sla_minutes * 1.5, replication_lag_sla_minutes + 30):
        replication = "WARN"
    else:
        replication = "FAIL"

    if last_run_status is None:
        pipeline = "UNKNOWN"
    elif last_run_status == "SUCCESS":
        pipeline = "OK"
    elif last_run_status == "RUNNING":
        pipeline = "RUNNING"
    else:
        pipeline = "FAIL"

    statuses = {freshness, replication, pipeline}
    known_statuses = statuses - {"UNKNOWN"}
    if "FAIL" in known_statuses:
        overall = "FAIL"
    elif "WARN" in known_statuses:
        overall = "WARN"
    elif known_statuses and known_statuses <= {"OK", "RUNNING"}:
        overall = "OK"
    else:
        overall = "UNKNOWN"

    weights = [(freshness, 40.0), (replication, 35.0), (pipeline, 25.0)]
    score = 0.0
    available = 0.0
    for status, weight in weights:
        if status == "UNKNOWN":
            continue
        available += weight
        if status in {"OK", "RUNNING"}:
            score += weight
        elif status == "WARN":
            score += weight * 0.5
    normalized = 100.0 * score / available if available else 0.0
    return HealthResult(freshness, replication, pipeline, overall, round(normalized, 2))
