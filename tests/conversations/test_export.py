from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from scripts.export_conversaciones_diagnostico import EXPORTS, build_archive


class FakeCursor:
    def __init__(self):
        self.description = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("SET TRANSACTION"):
            return
        if "FROM etl_control.conversation_sources WHERE source_name=" in sql:
            self.rows = [(1, 1, 2)]
        else:
            self.description = [SimpleNamespace(name="message_id"), SimpleNamespace(name="body")]
            self.rows = [("abc", "Texto privado\ncon otra línea")]

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchmany(self, size):
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows


class FakeConnection:
    def cursor(self):
        return FakeCursor()


class ConversationExportTests(unittest.TestCase):
    def test_complete_archive_has_manifest_and_full_text_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diag.zip"
            manifest = build_archive(FakeConnection(), output,
                                     "Chat de WhatsApp con Cygnus - Ventas.txt")
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(EXPORTS) | {"manifest.json", "README.txt",
                                                "contract/01_contract.sql"}, set(archive.namelist()))
                data = json.loads(archive.read("raw/messages.jsonl"))
                self.assertEqual(data["body"], "Texto privado\ncon otra línea")
                self.assertEqual(manifest["files"]["raw/messages.jsonl"]["rows"], 1)
                self.assertNotIn("password", archive.read("manifest.json").decode())
            with self.assertRaises(FileExistsError):
                build_archive(FakeConnection(), output,
                              "Chat de WhatsApp con Cygnus - Ventas.txt")


if __name__ == "__main__":
    unittest.main()
