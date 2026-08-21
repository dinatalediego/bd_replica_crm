from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "benchmark_separation_fall_30d.py"


def _script() -> str:
    return " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())


def test_benchmark_uses_governed_30d_training_view() -> None:
    text = _script()
    assert "features.separation_fall_training_30d" in text
    assert "target_fall_within_30d" in text
    assert "structural_temporal_30d_v1" in text


def test_benchmark_enforces_group_safe_out_of_time_split() -> None:
    text = _script()
    assert "test separation_id is removed from train" in text
    assert "group leakage detectado" in text
    assert "cross_regime_pre2026_to_post2026" in text
    assert "current_regime_2026_early_to_recent" in text


def test_benchmark_keeps_uncertified_interactions_out() -> None:
    text = _script()
    assert "interaction_features_certified" in text
    assert "days_since_last_interaction" not in text
    assert "interaction_count_14d" not in text


def test_benchmark_has_business_baselines_and_ml_challengers() -> None:
    text = _script()
    assert "prevalence_baseline" in text
    assert "landmark_prevalence_baseline" in text
    assert "logistic_regression" in text
    assert "random_forest" in text
    assert "hist_gradient_boosting" in text
    assert "average_precision_score" in text
    assert "brier_score_loss" in text


def test_advisor_is_opt_in_not_default() -> None:
    text = _script()
    assert "--include-advisor" in text
    assert 'categorical_features = ["codigo_proyecto", "tipo_unidad_principal"]' in text
