"""Behavior checks that do not require a database or optional connectors."""
import ast
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(tree, path, 'exec'), namespace)
    return namespace


def test_refresh_decisions():
    fn = load_functions('scripts/refresh_clientes_calidad.py', {'needs_refresh'}, {})['needs_refresh']
    now = datetime.now(timezone.utc)
    assert not fn(10, 10, now, now)
    assert not fn(10, 10, now, now + timedelta(seconds=1))
    assert fn(10, 10, now + timedelta(seconds=1), now)
    assert fn(11, 10, now, now)
    assert fn(9, 10, now, now)
    assert fn(10, 10, None, now)
    assert fn(10, 10, now, None)
    assert not fn(0, 0, None, None)


def test_second_instance_skips_all_steps_and_connection_closes():
    for acquired in (False, True):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = (acquired,)
        run = MagicMock(return_value=0)
        ns = load_functions('scripts/dw_refresh.py', {'pipeline_lock', 'main'}, {
            'contextmanager': contextmanager,
            'connect_postgres': MagicMock(return_value=conn),
            'load_settings': lambda: None,
            '_logger': MagicMock(),
            '_main_locked': run,
        })
        assert ns['main']() == 0
        assert run.call_count == int(acquired)
        assert conn.autocommit is True
        conn.__exit__.assert_called_once()


def test_lock_connection_closes_on_pipeline_error():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
    ns = load_functions('scripts/dw_refresh.py', {'pipeline_lock', 'main'}, {
        'contextmanager': contextmanager, 'connect_postgres': lambda _: conn,
        'load_settings': lambda: None, '_logger': MagicMock(),
        '_main_locked': MagicMock(side_effect=RuntimeError('failed')),
    })
    try:
        ns['main']()
    except RuntimeError:
        pass
    else:
        raise AssertionError('pipeline exception swallowed')
    conn.__exit__.assert_called_once()
