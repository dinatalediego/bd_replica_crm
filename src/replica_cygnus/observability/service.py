from __future__ import annotations

from pathlib import Path

from ..config import load_table_configs
from ..connections import connect_postgres, connect_redshift
from ..decision_schema import ensure_decision_intelligence
from ..sync import select_configs
from .collector import collect_asset_snapshot, register_asset
from .config import load_observability_config, monitoring_for_table
from .schema import ensure_observability


def run_observability(
    settings,
    table_config_path: Path,
    observability_config_path: Path,
    *,
    mode: str = "hourly",
    only: str | None = None,
    include_disabled: bool = False,
) -> list[dict]:
    table_configs = select_configs(
        load_table_configs(table_config_path),
        only=only,
        include_disabled=include_disabled,
    )
    defaults, assets = load_observability_config(observability_config_path)

    source = connect_redshift(settings)
    target = connect_postgres(settings)
    results: list[dict] = []
    try:
        ensure_decision_intelligence(target, settings.project_root)
        ensure_observability(target, settings.project_root)
        for cfg in table_configs:
            monitor = monitoring_for_table(cfg, defaults, assets)
            register_asset(target, cfg, monitor)
            results.append(collect_asset_snapshot(source, target, cfg, monitor, mode=mode))
    finally:
        source.close()
        target.close()
    return results


def register_all_assets(
    settings,
    table_config_path: Path,
    observability_config_path: Path,
) -> int:
    configs = load_table_configs(table_config_path)
    defaults, assets = load_observability_config(observability_config_path)
    with connect_postgres(settings) as target:
        ensure_decision_intelligence(target, settings.project_root)
        ensure_observability(target, settings.project_root)
        for cfg in configs:
            register_asset(target, cfg, monitoring_for_table(cfg, defaults, assets))
    return len(configs)
