"""Daily gate for the local WhatsApp export, evaluated in Lima time."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ScheduledResult:
    file_name: str
    status: str
    new_messages: int = 0
    new_events: int = 0
    run_id: int | None = None


def run_scheduled_import(conn, path: Path, importer: Callable) -> ScheduledResult:
    """Try until one import adds messages; resume on the next Lima calendar day.

    Import runs with zero new messages (including ruleset reclassification) do
    not consume the day's opportunity. The importer itself checks the export's
    SHA-256, validates the historical prefix, and serializes database writes.
    """
    if not path.is_file():
        raise FileNotFoundError(path)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM etl_control.conversation_import_runs AS r
                JOIN etl_control.conversation_sources AS s
                  ON s.source_id = r.source_id
                WHERE s.source_name = %s
                  AND r.new_messages > 0
                  AND (r.finished_at AT TIME ZONE 'America/Lima')::date =
                      (now() AT TIME ZONE 'America/Lima')::date
            )
            """,
            (path.name,),
        )
        imported_today = cur.fetchone()[0]

    if imported_today:
        return ScheduledResult(path.name, "SKIPPED_IMPORTED_TODAY")

    result = importer(conn, path)
    return ScheduledResult(result.file_name, result.status,
                           result.new_messages, result.new_events, result.run_id)
