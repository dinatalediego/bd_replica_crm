from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hourly_batch_delegates_to_single_dw_refresh_entrypoint() -> None:
    batch = (ROOT / "scripts" / "run_hourly.bat").read_text(encoding="utf-8").lower()

    assert "scripts\\dw_refresh.py" in batch
    assert "replica_cygnus.cli sync" not in batch


def test_dw_refresh_orders_layers_and_observability() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8").lower()

    raw_pos = code.index('"01_raw_sync"')
    schema_pos = code.index('"02_schema_sync"')
    core_pos = code.index('"03_core_commercial_refresh"')
    pbi_pos = code.index('"04_unidades_powerbi_refresh"')
    phase_b_pos = code.index('"05_absorption_phase_b_incremental"')
    lifecycle_pos = code.index('"06_core_lifecycle_contract"')
    pricing_pos = code.index('"07_pricing_projection"')
    matview_pos = code.index('"08_materialized_views"')
    observe_pos = code.index('"99_observability"')

    assert raw_pos < schema_pos < core_pos < pbi_pos < phase_b_pos < lifecycle_pos < pricing_pos < matview_pos < observe_pos


def test_schema_sync_tracks_checksums_and_repairs_missing_phase_b_qa() -> None:
    code = (ROOT / "scripts" / "schema_sync.py").read_text(encoding="utf-8").lower()

    assert "etl_control.schema_migrations" in code
    assert "hashlib.sha256" in code
    assert "03c_pago_ci_quality_override.sql" in code
    assert "analytics.run_sale_date_pago_ci_qa()" in code
    assert "to_regprocedure" in code


def test_materialized_view_refresh_covers_powerbi_serving_schemas() -> None:
    code = (ROOT / "scripts" / "refresh_materialized_views.py").read_text(encoding="utf-8").lower()

    assert '"core"' in code
    assert '"analytics"' in code
    assert '"analytics_compare"' in code
    assert '"gold"' in code
    assert "refresh materialized view" in code
