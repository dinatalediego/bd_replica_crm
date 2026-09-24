from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hourly_batch_delegates_to_single_dw_refresh_entrypoint() -> None:
    batch = (ROOT / "scripts" / "run_hourly.bat").read_text(encoding="utf-8").lower()

    assert "scripts\\dw_refresh.py" in batch
    assert "replica_cygnus.cli sync" not in batch


def test_dw_refresh_orders_layers_and_observability() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8").lower()

    raw_pos = code.index('"01_raw_sync"')
    archivos_pos = code.index('"01b_archivos_raw_sync"')
    schema_pos = code.index('"02_schema_sync"')
    core_pos = code.index('"03_core_commercial_refresh"')
    pbi_pos = code.index('"04_unidades_powerbi_refresh"')
    phase_b_pos = code.index('"05_absorption_phase_b_incremental"')
    lifecycle_pos = code.index('"06_core_lifecycle_contract"')
    pricing_pos = code.index('"07_pricing_projection"')
    matview_pos = code.index('"08_materialized_views"')
    observe_pos = code.index('"99_observability"')

    assert raw_pos < archivos_pos < schema_pos < core_pos < pbi_pos < phase_b_pos < lifecycle_pos < pricing_pos < matview_pos < observe_pos


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


def test_hourly_archivos_sync_is_versioned_and_safe() -> None:
    code = (ROOT / "scripts" / "dw_refresh.py").read_text(encoding="utf-8").lower()
    config = (ROOT / "config" / "hourly_required_tables.yml").read_text(encoding="utf-8").lower()

    assert "config/hourly_required_tables.yml" in code
    assert "source_table: archivos" in config
    assert "target_table: archivos" in config
    assert "strategy: full_refresh" in config
    assert "enabled: true" in config


def test_archivos_procesos_view_matches_power_query_contract() -> None:
    schema_sync = (ROOT / "scripts" / "schema_sync.py").read_text(encoding="utf-8").lower()
    sql = (ROOT / "sql" / "80_archivos_procesos" / "01_view.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert 'name="archivos_procesos"' in schema_sync
    assert "analytics.archivos_procesos" in schema_sync
    assert "create or replace view analytics.archivos_procesos" in sql
    assert "regularizar.pdf" in sql
    assert 'as "rank"' in sql
    assert "ranking_contrato" in sql
    assert "ranking_pasos" in sql
    assert "= 'contrato'" in sql
    assert "= 'proceso adquisicion'" in sql


def test_full_refresh_removes_obsolete_replica_unique_indexes() -> None:
    code = (ROOT / "src" / "replica_cygnus" / "target_schema.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "def _drop_managed_unique_indexes" in code
    assert "if cfg.key_columns and cfg.strategy == \"incremental\"" in code
    assert "_drop_managed_unique_indexes(conn, cfg)" in code


def test_archivos_procesos_classifies_contrato_filenames() -> None:
    sql = (ROOT / "sql" / "80_archivos_procesos" / "01_view.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "create table if not exists analytics.archivos_contrato_patrones" in sql
    assert "analytics.archivos_contrato_patrones" in sql
    assert "nombre_normalizado" in sql
    assert "es_convenio_separacion" in sql
    assert "es_carta_aprobacion" in sql
    assert "es_contrato_minuta" in sql
    assert "tipo_contrato_archivo" in sql

    # Patrones observados en los casos reales compartidos.
    assert "'convenio'" in sql
    assert "'pendiente de carta'" in sql
    assert "'carta'" in sql
    assert "'minuta'" in sql
    assert "'contrato'" in sql

    # Solo archivos cuyo montaje sea Contrato pueden clasificarse.
    assert "lower(btrim(coalesce(n.montaje::text, ''))) = 'contrato'" in sql
    assert "p.activo" in sql
    assert "position(' ' || p.patron || ' ' in ' ' || n.nombre_normalizado || ' ')" in sql

    # Si no hay una única categoría detectable, el resultado debe quedar incierto.
    assert "<> 1 then 'incierto'" in " ".join(sql.split())


def test_archivos_procesos_appends_classifier_columns_after_existing_rank_contract() -> None:
    sql = (ROOT / "sql" / "80_archivos_procesos" / "01_view.sql").read_text(
        encoding="utf-8"
    ).lower()

    rank_pos = sql.index('as "rank"')
    ranking_contrato_pos = sql.index("end as ranking_contrato")
    ranking_pasos_pos = sql.index("end as ranking_pasos")
    nombre_normalizado_pos = sql.index("as nombre_normalizado")

    assert rank_pos < ranking_contrato_pos < ranking_pasos_pos < nombre_normalizado_pos


def test_archivos_procesos_treats_regul_as_blank_document() -> None:
    sql = (ROOT / "sql" / "80_archivos_procesos" / "01_view.sql").read_text(
        encoding="utf-8"
    ).lower()

    assert "position('regul' in lower(coalesce(f.nombre::text, ''))) > 0" in sql
