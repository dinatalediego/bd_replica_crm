from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]


def _load_refresh_module():
    path = ROOT / "scripts" / "dw_refresh.py"
    spec = importlib.util.spec_from_file_location("night002_dw_refresh", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_windows_scheduler_has_one_canonical_dw_entrypoint():
    batch = (ROOT / "scripts" / "run_hourly.bat").read_text(encoding="utf-8").lower()
    assert batch.count("dw_refresh.py") == 1
    assert "replica_cygnus.cli" not in batch
    assert "--mode hourly" in batch


def test_hourly_source_step_is_due_only_and_single():
    module = _load_refresh_module()
    steps = module._steps("hourly")
    source_steps = [
        step for step in steps
        if "replica_cygnus.cli" in step.args and "sync" in step.args
    ]
    assert len(source_steps) == 1
    assert source_steps[0].args.count("--due-only") == 1
    assert "--additional-config" in source_steps[0].args


def test_local_only_has_no_source_sync():
    module = _load_refresh_module()
    steps = module._steps("hourly", local_only=True)
    assert all(
        not ("replica_cygnus.cli" in step.args and "sync" in step.args)
        for step in steps
    )


def test_marketing_audiences_run_after_client_quality_without_source_call():
    module = _load_refresh_module()
    steps = module._steps("hourly", local_only=True)
    names = [step.name for step in steps]
    assert names.count("02c_marketing_audiences_refresh") == 1
    assert names.index("02b_clientes_calidad_refresh") < names.index(
        "02c_marketing_audiences_refresh"
    )
    marketing = next(step for step in steps if step.name == "02c_marketing_audiences_refresh")
    assert marketing.args[-1].endswith("refresh_marketing_audiences.py")
