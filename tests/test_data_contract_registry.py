from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_datos_extras_contract_certifies_composite_grain() -> None:
    raw = yaml.safe_load((ROOT / "config" / "data_contracts.yml").read_text(encoding="utf-8"))
    contract = raw["contracts"]["raw_cygnus.datos_extras"]

    assert contract["grain"] == ["id", "nombre"]
    assert contract["requirements"]["replica_key_columns"] == ["id", "nombre"]
    assert contract["certification_evidence"]["duplicate_id_groups"] > 0
    assert contract["certification_evidence"]["duplicate_id_nombre_groups"] == 0
    assert contract["certification_evidence"]["incomplete_id_nombre_keys"] == 0


def test_tables_example_uses_certified_datos_extras_key() -> None:
    raw = yaml.safe_load((ROOT / "config" / "tables.example.yml").read_text(encoding="utf-8"))
    rows = raw["tables"]
    datos_extras = next(row for row in rows if row["source_table"] == "datos_extras")

    assert datos_extras["key_columns"] == ["id", "nombre"]
    assert datos_extras["watermark_column"] == "fecha_actualizacion"
    assert datos_extras["strategy"] == "incremental"
