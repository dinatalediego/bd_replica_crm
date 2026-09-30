from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from replica_cygnus import cli
from replica_cygnus.models import TableConfig
from replica_cygnus.source_gate import is_due, merged_configs, watch_rows

NOW = datetime(2026, 9, 30, 22, tzinfo=timezone.utc)


def cfg(strategy="incremental"):
    return TableConfig(source_schema="grupocygnus", source_table="clientes", strategy=strategy,
                       key_columns=["id"], watermark_column="fecha_actualizacion", enabled=True)


@pytest.mark.parametrize("hours,expected", [(3.99, False), (4, True), (5, True)])
def test_incremental_uses_elapsed_time_after_missed_trigger(monkeypatch, hours, expected):
    monkeypatch.delenv("REDSHIFT_SYNC_INTERVAL_HOURS", raising=False)
    assert is_due(cfg(), NOW - timedelta(hours=hours), NOW) is expected


def test_full_refresh_daily_and_unknown_state(monkeypatch):
    monkeypatch.delenv("REDSHIFT_FULL_SYNC_INTERVAL_HOURS", raising=False)
    assert not is_due(cfg("full_refresh"), NOW - timedelta(hours=5), NOW)
    assert is_due(cfg("full_refresh"), NOW - timedelta(hours=24), NOW)
    assert is_due(cfg(), None, NOW)


def test_primary_disabled_configuration_wins(tmp_path):
    primary = tmp_path / "primary.yml"
    extra = tmp_path / "extra.yml"
    text = "tables:\n  - source_schema: grupocygnus\n    source_table: archivos\n    strategy: full_refresh\n    enabled: "
    primary.write_text(text + "false\n")
    extra.write_text(text + "true\n")
    merged = merged_configs(primary, (extra,))
    assert len(merged) == 1 and not merged[0].enabled


def test_no_due_tables_means_no_redshift_connection(monkeypatch):
    target = MagicMock()
    target.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    source = MagicMock(side_effect=AssertionError("Redshift must stay closed"))
    monkeypatch.setattr(cli, "connect_postgres", lambda settings: target)
    monkeypatch.setattr(cli, "connect_redshift", source)
    monkeypatch.setattr(cli, "ensure_control_tables", lambda conn: None)
    from replica_cygnus import source_gate
    monkeypatch.setattr(source_gate, "merged_configs", lambda *args: [cfg()])
    monkeypatch.setattr(source_gate, "due_configs", lambda *args: [])
    assert cli.command_sync(None, Path("unused"), None, False, None, False, due_only=True) == 0
    source.assert_not_called()
    target.close.assert_called_once()


def test_gate_lock_denied_does_not_connect(monkeypatch):
    target = MagicMock()
    target.cursor.return_value.__enter__.return_value.fetchone.return_value = (False,)
    source = MagicMock(side_effect=AssertionError("Redshift must stay closed"))
    monkeypatch.setattr(cli, "connect_postgres", lambda settings: target)
    monkeypatch.setattr(cli, "connect_redshift", source)
    monkeypatch.setattr(cli, "ensure_control_tables", lambda conn: None)
    from replica_cygnus import source_gate
    monkeypatch.setattr(source_gate, "merged_configs", lambda *args: [cfg()])
    assert cli.command_sync(None, Path("unused"), None, False, None, False, due_only=True) == 1
    source.assert_not_called()


def test_watch_keeps_failure_visible_even_with_recent_success(monkeypatch):
    from replica_cygnus import source_gate
    target = MagicMock()
    monkeypatch.setattr(source_gate, "connect_postgres", lambda settings: target)
    monkeypatch.setattr(source_gate, "ensure_control_tables", lambda conn: None)
    monkeypatch.setattr(source_gate, "merged_configs", lambda *args: [cfg()])
    monkeypatch.setattr(source_gate, "ledger", lambda *args: (NOW, "2026-09-30", 10, NOW, "FAILED", "timeout"))
    assert watch_rows(SimpleNamespace(), Path("unused"))[0][4] == "FAILED"


def test_due_subset_reuses_one_source_connection(monkeypatch):
    target, source = MagicMock(), MagicMock()
    target.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    connect = MagicMock(return_value=source)
    monkeypatch.setattr(cli, "connect_postgres", lambda settings: target)
    monkeypatch.setattr(cli, "connect_redshift", connect)
    monkeypatch.setattr(cli, "ensure_control_tables", lambda conn: None)
    from replica_cygnus import source_gate
    first, second = cfg(), cfg("full_refresh")
    second.source_table = "archivos"
    monkeypatch.setattr(source_gate, "merged_configs", lambda *args: [first, second])
    monkeypatch.setattr(source_gate, "due_configs", lambda *args: [first])
    result = SimpleNamespace(status="SUCCESS", source_name=first.source_name, target_name=first.target_name,
                             rows_extracted=0, rows_loaded=0, watermark_after="today", message="")
    sync = MagicMock(return_value=result)
    monkeypatch.setattr(cli, "sync_table", sync)
    assert cli.command_sync(None, Path("unused"), None, False, None, False, due_only=True) == 0
    connect.assert_called_once()
    sync.assert_called_once_with(source, target, first, max_rows=None, dry_run=False)
    source.close.assert_called_once()


def test_watch_settings_work_without_source_credentials(monkeypatch, tmp_path):
    from replica_cygnus.settings import load_settings
    for key in ("HOST", "DATABASE", "USER", "PASSWORD"):
        monkeypatch.delenv("REDSHIFT_" + key, raising=False)
        monkeypatch.setenv("POSTGRES_" + key, "local-test")
    settings = load_settings(tmp_path, require_source=False)
    assert settings.redshift.host == ""
    assert settings.postgres.host == "local-test"


def test_local_only_master_never_schedules_source_sync():
    import importlib.util
    import sys
    path = Path(__file__).resolve().parents[1] / "scripts" / "dw_refresh.py"
    spec = importlib.util.spec_from_file_location("dw_refresh_gate_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    steps = module._steps("hourly", local_only=True)
    assert steps and all("replica_cygnus.cli" not in step.args for step in steps)
    normal = module._steps("hourly")
    assert normal[0].args.count("--due-only") == 1
    assert "--additional-config" in normal[0].args
