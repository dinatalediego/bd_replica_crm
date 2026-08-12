from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..models import TableConfig


@dataclass(frozen=True)
class AssetMonitoringConfig:
    criticality: str = "high"
    business_domain: str = "Commercial Analytics"
    business_process: str = "CRM / Funnel Comercial"
    business_owner: str = "Inteligencia de Negocios"
    business_impact: str = "Afecta la confiabilidad de reportes y decisiones comerciales."
    downstream_products: str = "Power BI"
    expected_frequency_minutes: int = 60
    freshness_sla_minutes: int = 90
    replication_lag_sla_minutes: int = 90
    reconciliation_tolerance_pct: float = 1.0
    monitor_source_watermark: bool = True
    deep_quality_enabled: bool = True

    def __post_init__(self) -> None:
        if self.criticality.lower() not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"criticality no soportada: {self.criticality}")
        if self.expected_frequency_minutes <= 0:
            raise ValueError("expected_frequency_minutes debe ser > 0")
        if self.freshness_sla_minutes <= 0:
            raise ValueError("freshness_sla_minutes debe ser > 0")
        if self.replication_lag_sla_minutes < 0:
            raise ValueError("replication_lag_sla_minutes no puede ser negativo")
        if self.reconciliation_tolerance_pct < 0:
            raise ValueError("reconciliation_tolerance_pct no puede ser negativo")


def _merge(defaults: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update({k: v for k, v in row.items() if v is not None})
    return merged


def load_observability_config(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.exists():
        return {}, {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults", {}) or {}
    assets = raw.get("assets", {}) or {}
    if not isinstance(defaults, dict) or not isinstance(assets, dict):
        raise ValueError("observability.yml debe contener defaults y assets como objetos YAML")
    return defaults, assets


def monitoring_for_table(
    cfg: TableConfig,
    defaults: dict[str, Any],
    assets: dict[str, dict[str, Any]],
) -> AssetMonitoringConfig:
    specific = assets.get(cfg.source_name) or assets.get(cfg.source_table) or {}
    data = _merge(defaults, specific)
    return AssetMonitoringConfig(**data)
