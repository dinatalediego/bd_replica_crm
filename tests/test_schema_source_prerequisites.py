from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_schema_sync():
    path = ROOT / "scripts/schema_sync.py"
    spec = spec_from_file_location("schema_sync_prereq_test", path)
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_archivos_component_declares_raw_source_prerequisite():
    module = load_schema_sync()
    component = next(c for c in module.COMPONENTS if c.name == "archivos_procesos")
    assert component.required_relations == ("raw_cygnus.archivos",)


def test_missing_raw_source_defers_component_without_executing_sql(monkeypatch, capsys):
    module = load_schema_sync()
    component = next(c for c in module.COMPONENTS if c.name == "archivos_procesos")
    conn = MagicMock()
    monkeypatch.setattr(module, "_missing_required_relations", lambda *_: ["raw_cygnus.archivos"])
    monkeypatch.setattr(module, "_checksum", MagicMock(side_effect=AssertionError("SQL path should not be read")))

    result = module._apply_component(conn, ROOT, component, force=False)

    assert result == "DEFERRED"
    assert "[SCHEMA][DEFER] archivos_procesos" in capsys.readouterr().out
    conn.cursor.assert_not_called()


def test_schema_summary_tracks_deferred_sources():
    code = (ROOT / "scripts/schema_sync.py").read_text(encoding="utf-8")
    assert 'deferred += result == "DEFERRED"' in code
    assert "waiting_source={deferred}" in code
