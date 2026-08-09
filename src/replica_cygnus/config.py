from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError
from .models import TableConfig, merge_dicts


def load_table_configs(config_path: Path) -> list[TableConfig]:
    if not config_path.exists():
        raise ConfigurationError(
            f"No existe {config_path}. Copia config/tables.example.yml como config/tables.yml."
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    defaults: dict[str, Any] = raw.get("defaults", {}) or {}
    table_rows = raw.get("tables", []) or []
    if not isinstance(table_rows, list):
        raise ConfigurationError("La clave 'tables' debe ser una lista.")

    configs: list[TableConfig] = []
    for index, row in enumerate(table_rows, start=1):
        if not isinstance(row, dict):
            raise ConfigurationError(f"tables[{index}] debe ser un objeto YAML.")
        data = merge_dicts(defaults, row)
        try:
            configs.append(TableConfig(**data))
        except TypeError as exc:
            raise ConfigurationError(f"Error en tables[{index}]: {exc}") from exc
    return configs
