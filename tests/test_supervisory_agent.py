from replica_cygnus.supervisory_agent import summarize_platform


def test_summarize_platform_ok():
    rows = [
        ("Replica", "data", "HIGH", 1.0, "DONE", 4, 4),
        ("Observability", "control", "HIGH", 0.9, "OK", 3, 3),
    ]
    health = summarize_platform(rows)
    assert health.status == "OK"
    assert health.score == 95.0
    assert "estable" in health.summary.lower()


def test_summarize_platform_warn():
    rows = [
        ("Replica", "data", "HIGH", 1.0, "DONE", 4, 4),
        ("Quality", "control", "MEDIUM", 0.5, "IN_PROGRESS", 2, 4),
    ]
    health = summarize_platform(rows)
    assert health.status == "WARN"
    assert health.score == 75.0
    assert "Quality" in health.summary


def test_summarize_platform_fail():
    rows = [
        ("ETL", "data", "CRITICAL", 0.2, "BLOCKED", 1, 5),
        ("Observability", "control", "HIGH", 1.0, "DONE", 3, 3),
    ]
    health = summarize_platform(rows)
    assert health.status == "FAIL"
    assert health.score == 60.0
    assert "ETL" in health.summary


def test_summarize_platform_unknown_without_evidence():
    health = summarize_platform([])
    assert health.status == "UNKNOWN"
    assert health.score == 0.0
