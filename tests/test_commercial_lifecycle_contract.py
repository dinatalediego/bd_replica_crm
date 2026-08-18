from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_lifecycle_is_governed_projection_not_duplicate_logic() -> None:
    sql = (ROOT / "sql" / "init_core_commercial_lifecycle.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "create or replace view core.fact_ciclo_comercial_unidad" in normalized
    assert "from analytics.int_ciclo_comercial_unidad" in normalized
    assert "create or replace view core.v_ciclo_comercial_health" in normalized
    assert "codigo_proforma" in normalized
    assert "codigo_unidad" in normalized
    assert "resultado_ciclo" in normalized


def test_hourly_pipeline_refreshes_raw_core_lifecycle_then_observes() -> None:
    batch = (ROOT / "scripts" / "run_hourly.bat").read_text(encoding="utf-8").lower()

    sync_pos = batch.index("replica_cygnus.cli sync")
    core_pos = batch.index("scripts\\core_commercial.py\" refresh")
    lifecycle_pos = batch.index("src\\absorption_phase_b\\run_incremental.py")
    observe_pos = batch.index("replica_cygnus.cli observe --mode hourly")

    assert sync_pos < core_pos < lifecycle_pos < observe_pos


def test_incremental_runner_calls_phase_b_incremental_procedure() -> None:
    runner = (ROOT / "src" / "absorption_phase_b" / "run_incremental.py").read_text(encoding="utf-8")

    assert "refresh_absorption_phase_b_incremental" in runner
    assert "ABSORPTION_PHASE_B_LOOKBACK_DAYS" in runner
