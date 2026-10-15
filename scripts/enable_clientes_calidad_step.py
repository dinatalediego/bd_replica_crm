"""Re-enable only the temporarily commented DQ Step; preserve other local repairs."""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAME = '02b_clientes_calidad_refresh'


def count_steps(code: str) -> int:
    tree = ast.parse(code)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_steps')
    return sum(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'Step'
        and bool(n.args) and isinstance(n.args[0], ast.Constant) and n.args[0].value == NAME
        for n in ast.walk(fn)
    )


def enable(code: str) -> str:
    count = count_steps(code)
    if count == 1:
        return code
    if count != 0:
        raise ValueError('Hay mas de un Step 02b; revisar el orquestador.')
    # Only the known four-line commented block from the Windows recovery.
    pattern = re.compile(
        r'(?m)^(?P<indent>[ \t]*)#[ \t]?Step\(\r?\n'
        r'[ \t]*#[ \t]+["\']02b_clientes_calidad_refresh["\'],\r?\n'
        r'[ \t]*#[ \t]+\(py, str\(ROOT / ["\']scripts["\'] / ["\']refresh_clientes_calidad.py["\']\)\),\r?\n'
        r'[ \t]*#[ \t]*\),[ \t]*(?:\r?\n|$)'
    )
    def replacement(match):
        indent = match.group('indent')
        return (f'{indent}Step(\n{indent}    "{NAME}",\n'
                f'{indent}    (py, str(ROOT / "scripts" / "refresh_clientes_calidad.py")),\n'
                f'{indent}),\n')
    result, found = pattern.subn(replacement, code)
    if found != 1 or count_steps(result) != 1:
        raise ValueError('No encontre el bloque temporal conocido. Revisar Step 02b manualmente; archivo intacto.')
    compile(result, 'dw_refresh.py', 'exec')
    return result


def main() -> int:
    path = ROOT / 'scripts/dw_refresh.py'
    code = path.read_text(encoding='utf-8-sig')
    result = enable(code)
    if result == code:
        print('02b ya esta activo; orquestador intacto.')
        return 0
    backup = path.with_name(f'dw_refresh.py.backup_{datetime.now():%Y%m%d_%H%M%S_%f}')
    backup.write_bytes(path.read_bytes())
    path.write_text(result, encoding='utf-8')
    print(f'02b incremental activado. Respaldo: {backup.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
