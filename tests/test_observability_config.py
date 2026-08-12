from pathlib import Path

from replica_cygnus.models import TableConfig
from replica_cygnus.observability.config import load_observability_config, monitoring_for_table


def test_observability_specific_table_overrides_defaults(tmp_path: Path):
    path = tmp_path / "observability.yml"
    path.write_text(
        """
defaults:
  criticality: high
  freshness_sla_minutes: 90
assets:
  procesos:
    criticality: critical
    freshness_sla_minutes: 75
""",
        encoding="utf-8",
    )
    defaults, assets = load_observability_config(path)
    cfg = TableConfig(
        source_schema="grupocygnus",
        source_table="procesos",
        key_columns=["id"],
        watermark_column="fecha_actualizacion",
    )
    monitor = monitoring_for_table(cfg, defaults, assets)
    assert monitor.criticality == "critical"
    assert monitor.freshness_sla_minutes == 75
