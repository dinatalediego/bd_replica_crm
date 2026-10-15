from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from replica_cygnus.conversations.schedule import run_scheduled_import


class FakeCursor:
    def __init__(self, imported_today):
        self.imported_today = imported_today
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.query, self.params = query, params

    def fetchone(self):
        return (self.imported_today,)


class FakeConn:
    def __init__(self, imported_today):
        self.cur = FakeCursor(imported_today)

    def cursor(self):
        return self.cur


class ScheduledImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'Chat de WhatsApp con Cygnus - Ventas.txt'
        self.path.write_text('export', encoding='utf-8')

    def test_successful_import_today_skips_even_if_txt_has_changed(self):
        conn = FakeConn(True)

        def forbidden_import(*_):
            self.fail('A second import on the same Lima day is forbidden')

        result = run_scheduled_import(conn, self.path, forbidden_import)
        self.assertEqual(result.status, 'SKIPPED_IMPORTED_TODAY')
        self.assertIn('r.new_messages > 0', conn.cur.query)
        self.assertIn("AT TIME ZONE 'America/Lima'", conn.cur.query)
        self.assertEqual(conn.cur.params, (self.path.name,))

    def test_no_new_messages_does_not_consume_the_day(self):
        calls = []

        def importer(conn, path):
            calls.append((conn, path))
            return SimpleNamespace(file_name=path.name, status='UNCHANGED',
                                   new_messages=0, new_events=0, run_id=None)

        conn = FakeConn(False)
        for _ in range(3):
            result = run_scheduled_import(conn, self.path, importer)
            self.assertEqual(result.status, 'UNCHANGED')
        self.assertEqual(len(calls), 3)

    def test_imported_messages_recorded_for_next_attempt(self):
        result = run_scheduled_import(
            FakeConn(False), self.path,
            lambda conn, path: SimpleNamespace(file_name=path.name, status='IMPORTED',
                                               new_messages=5, new_events=3, run_id=7),
        )
        self.assertEqual((result.new_messages, result.run_id), (5, 7))

    def test_missing_source_is_a_visible_failure(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            run_scheduled_import(FakeConn(False), self.path, lambda *_: None)


if __name__ == '__main__':
    unittest.main()
