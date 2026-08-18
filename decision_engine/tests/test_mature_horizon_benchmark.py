from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "benchmark_separation_fall_30d_mature.py"


def _text() -> str:
    return " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())


def test_binary_benchmark_requires_complete_30_day_horizon() -> None:
    text = _text()
    assert "horizon_end_at <= a.observed_through" in text
    assert "labeled_rows_removed_for_incomplete_horizon" in text
    assert "positive_rows_removed_for_incomplete_horizon" in text


def test_global_snapshot_top_k_is_not_presented_as_operational_metric() -> None:
    text = _text()
    assert "global snapshot top-k is prohibited" in text
    assert "first_touch_metrics.csv" in text
    assert "daily operational ranking requires a separate daily risk-set backtest" in text


def test_first_touch_research_ranking_has_one_row_per_separation() -> None:
    text = _text()
    assert "first_eligible_test_snapshot_per_separation" in text
    assert ".groupby(group, as_index=false, sort=false) .head(1)" in text


def test_mature_benchmark_preserves_group_and_feature_safety() -> None:
    text = _text()
    assert "base.split_group_safe" in text
    assert "base.prohibited_features" in text
    assert "interaction_features_certified=false" in text
