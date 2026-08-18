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
    assert "fecha_pago_ci" in normalized
    assert "fecha_cierre_proceso_venta" in normalized
    assert "ventas_post_2026_sin_pago_ci" in normalized


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


def test_phase_b_installs_pago_ci_override_after_base_full_refresh() -> None:
    install = (ROOT / "src" / "absorption_phase_b" / "install.py").read_text(encoding="utf-8")

    base_pos = install.index('"03_refresh_full.sql"')
    override_pos = install.index('"03b_sale_date_pago_ci.sql"')
    incremental_pos = install.index('"05_incremental.sql"')

    assert base_pos < override_pos < incremental_pos


def test_sale_date_rule_prioritizes_pago_ci_and_limits_legacy_fallback() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03b_sale_date_pago_ci.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(sql.lower().split())

    assert "pago_ci_datos_extras" in normalized
    assert "fecha_pago_ci" in normalized
    assert "fecha_separacion < date '2026-01-01'" in normalized
    assert "legacy_fecha_firma_pre_2026" in normalized
    assert "post_2026_sale_without_pago_ci" in normalized
    assert "open_residential_cycle_with_pago_ci" in normalized
    assert "rename to refresh_absorption_phase_b_full_base" in normalized


def test_fecha_de_minuta_is_not_sale_evidence_in_v2_override() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03b_sale_date_pago_ci.sql").read_text(
        encoding="utf-8"
    )
    # It is allowed in documentation/comments as a separate milestone, but the
    # executable sale method must never reintroduce the old FECHA_DE_MINUTA mode.
    assert "'FECHA_DE_MINUTA'" not in sql
