from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MarketSource:
    source_id: str
    empresa_fuente: str
    codigo_proyecto: str
    nombre_proyecto: str
    sheet_name: str | None = None
    header_row: int = 1
    timezone: str = "America/Lima"


def load_source(project_root: Path, source_id: str) -> MarketSource:
    path = project_root / "config" / "mercado_sources.yml"
    if not path.exists():
        raise FileNotFoundError(f"No existe la configuración: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = (payload.get("sources") or {}).get(source_id)
    if not raw:
        raise KeyError(f"No existe source_id={source_id!r} en {path}")

    return MarketSource(
        source_id=source_id,
        empresa_fuente=str(raw["empresa_fuente"]).strip(),
        codigo_proyecto=str(raw["codigo_proyecto"]).strip(),
        nombre_proyecto=str(raw["nombre_proyecto"]).strip(),
        sheet_name=(str(raw["sheet_name"]).strip() if raw.get("sheet_name") else None),
        header_row=int(raw.get("header_row", 1)),
        timezone=str(raw.get("timezone", "America/Lima")).strip(),
    )

