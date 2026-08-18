from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_lifecycle_is_governed_projection_not_duplicate_logic() -> None:
    sql = (ROOT / "sql" / "init_core_commercial_lifecycle.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "create or replace view core.fact_ciclo_comercial_unidad" in normalized
    assert "from analytics.int_ciclo_comercial_unidad" in normalized
    assert "create or replace view core.v_ciclo_comercial_health" in normalized
    assert "fecha_de_minuta as fecha_pago_ci" in normalized
    assert "pago_ci_marker_confirmado" in normalized
    assert "pago_ci_marker_desconocido" in normalized
    assert "fecha_cierre_proceso_venta" in normalized
    assert "ventas_post_2026_sin_pago_ci" in normalized


def test_hourly_pipeline_refreshes_raw_core_lifecycle_then_observes() -> None:
    batch = (ROOT / "scripts" / "run_hourly.bat").read_text(encoding="utf-8").lower()

    sync_pos = batch.index("replica_cygnus.cli sync")
    core_pos = batch.index("scripts\\core_commercial.py\" refresh")
    lifecycle_pos = batch.index("src\\absorption_phase_b\\run_incremental.py")
    observe_pos = batch.index("replica_cygnus.cli observe --mode hourly")

    assert sync_pos < core_pos < lifecycle_pos < observe_pos


def test_incremental_runner_calls_phase_b_incremental_and_conversion_qa() -> None:
    runner = (ROOT / "src" / "absorption_phase_b" / "run_incremental.py").read_text(encoding="utf-8")

    assert "refresh_absorption_phase_b_incremental" in runner
    assert "run_sale_date_pago_ci_qa" in runner
    assert "ABSORPTION_PHASE_B_LOOKBACK_DAYS" in runner


def test_phase_b_installs_semantic_correction_after_base_full_refresh() -> None:
    install = (ROOT / "src" / "absorption_phase_b" / "install.py").read_text(encoding="utf-8")

    base_pos = install.index('"03_refresh_full.sql"')
    correction_pos = install.index('"03b_sale_date_pago_ci.sql"')
    qa_pos = install.index('"03c_pago_ci_quality_override.sql"')
    incremental_pos = install.index('"05_incremental.sql"')

    assert base_pos < correction_pos < qa_pos < incremental_pos


def test_mistaken_pago_ci_date_override_is_removed() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03b_sale_date_pago_ci.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.lower().split())

    assert "pago_ci is not a date" in normalized
    assert "drop procedure if exists analytics.apply_sale_date_pago_ci_rule" in normalized
    assert "refresh_absorption_phase_b_full_base" in normalized
    assert "authoritative fecha_pago_ci is fecha_de_minuta via core" in normalized


def test_conversion_quality_contract_separates_marker_from_date() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.lower().split())

    assert "fecha_pago_ci_parse_error" in normalized
    assert "pago_ci_unknown_marker_value" in normalized
    assert "pago_ci_marker_without_fecha_pago_ci" in normalized
    assert "fecha_pago_ci_without_marker" in normalized
    assert "fecha_pago_ci_not_prioritized_as_sale_date" in normalized
    assert "post_2026_sale_without_fecha_pago_ci" in normalized
    assert "open_residential_cycle_with_fecha_pago_ci" in normalized
    assert "pagó cuota inicial (minuta)" in normalized
