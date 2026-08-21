from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_maturity_control_tables_exist_in_sql_contract() -> None:
    sql = _normalized(ROOT / "sql" / "03_decision_maturity_control.sql")
    assert "decision_intelligence.policy_registry" in sql
    assert "decision_intelligence.decision_run" in sql
    assert "decision_intelligence.experiment_registry" in sql
    assert "decision_intelligence.production_incident" in sql
    assert "v_decision_value_scorecard" in sql
    assert "v_policy_operational_health" in sql


def test_baseline_is_seeded_as_shadow_not_active() -> None:
    sql = _normalized(ROOT / "sql" / "04_seed_separation_policy.sql")
    assert "'separation_fall_risk'" in sql
    assert "'separation-fall-risk-baseline-v0.1.0'" in sql
    assert "'shadow'" in sql
    assert "'active'" not in sql


def test_install_includes_policyops_before_feature_runtime() -> None:
    cli = _normalized(ROOT / "src" / "cygnus_decision_engine" / "cli.py")
    assert "03_decision_maturity_control.sql" in cli
    assert "04_seed_separation_policy.sql" in cli
    assert cli.index("03_decision_maturity_control.sql") < cli.index("02_separation_fall_risk_features.sql")


def test_run_defaults_to_dry_run_and_live_is_explicit() -> None:
    cli = _normalized(ROOT / "src" / "cygnus_decision_engine" / "cli.py")
    assert 'return "dry_run"' in cli
    assert 'if getattr(args, "live", false)' in cli
    assert 'if getattr(args, "shadow", false)' in cli


def test_shadow_status_does_not_enter_active_worklist() -> None:
    runtime_sql = _normalized(ROOT / "sql" / "01_separation_fall_risk_runtime.sql")
    contracts = _normalized(ROOT / "src" / "cygnus_decision_engine" / "contracts.py")
    assert 'status: literal["active", "shadow", "blocked", "expired"]' in contracts
    assert "where status = 'active'" in runtime_sql
