import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('enable_dq', ROOT / 'scripts/enable_clientes_calidad_step.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


BASE = '''def _steps(mode, local_only=False):
    py = 'python'
    return (
        Step("02_schema_sync", (py, "schema.py")),
        # Step(
        #     "02b_clientes_calidad_refresh",
        #     (py, str(ROOT / "scripts" / "refresh_clientes_calidad.py")),
        # ),
        Step("02c_portal_conversion_refresh", (py, "local-fixed-portal.py")),
    )
'''


def test_enable_known_block_keeps_local_portal_repair():
    result = module.enable(BASE)
    assert module.count_steps(result) == 1
    assert 'local-fixed-portal.py' in result
    assert result.split('Step("02c_portal')[1] == BASE.split('Step("02c_portal')[1]
    assert module.enable(result) == result


def test_unknown_orchestrator_is_rejected():
    with pytest.raises((ValueError, StopIteration)):
        module.enable('def main(): pass')
    with pytest.raises(ValueError, match='archivo intacto'):
        module.enable(BASE.replace('# Step(', '# DIFFERENT('))


def test_repository_orchestrator_has_executable_dq_step():
    assert module.count_steps((ROOT / 'scripts/dw_refresh.py').read_text()) == 1
