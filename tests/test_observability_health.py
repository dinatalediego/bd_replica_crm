from replica_cygnus.observability.health import classify_health


def test_health_ok_when_fresh_and_synced():
    result = classify_health(
        minutes_since_success=30,
        freshness_sla_minutes=90,
        replication_lag_minutes=10,
        replication_lag_sla_minutes=90,
        last_run_status="SUCCESS",
    )
    assert result.health_status == "OK"
    assert result.score == 100.0


def test_health_fails_when_pipeline_failed():
    result = classify_health(
        minutes_since_success=30,
        freshness_sla_minutes=90,
        replication_lag_minutes=10,
        replication_lag_sla_minutes=90,
        last_run_status="FAILED",
    )
    assert result.pipeline_status == "FAIL"
    assert result.health_status == "FAIL"


def test_health_warns_near_freshness_boundary():
    result = classify_health(
        minutes_since_success=110,
        freshness_sla_minutes=90,
        replication_lag_minutes=20,
        replication_lag_sla_minutes=90,
        last_run_status="SUCCESS",
    )
    assert result.freshness_status == "WARN"
    assert result.health_status == "WARN"


def test_unknown_replication_is_neutral_for_full_refresh_style_asset():
    result = classify_health(
        minutes_since_success=20,
        freshness_sla_minutes=90,
        replication_lag_minutes=None,
        replication_lag_sla_minutes=90,
        last_run_status="SUCCESS",
    )
    assert result.replication_status == "UNKNOWN"
    assert result.health_status == "OK"
    assert result.score == 100.0
