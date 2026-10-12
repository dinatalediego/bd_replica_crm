"""Append-only ingestion with a strict export-prefix contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .extraction import RULESET_VERSION, extract_linked_events
from .parser import Message, parse_export


class HistoricalExportChanged(ValueError):
    """An existing message was edited, removed or inserted before the previous tail."""


@dataclass(frozen=True)
class ImportResult:
    file_name: str
    status: str
    parsed_messages: int
    new_messages: int
    new_events: int
    run_id: int | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunks(items: list, size: int):
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


def validate_append_only(messages: list[Message], old_ids: list[str]) -> list[Message]:
    """Return only the suffix, or fail on any historical edit/insertion/deletion."""
    mismatch = next((i for i, old_id in enumerate(old_ids, 1)
                     if i > len(messages) or messages[i - 1].message_id != old_id), None)
    if mismatch is not None:
        raise HistoricalExportChanged(
            f"El mensaje ordinal {mismatch} cambió, se insertó o se eliminó en el historial. "
            "Se abortó sin escrituras; comparar las exportaciones antes de reconciliar."
        )
    return messages[len(old_ids):]


def import_export(conn, path: Path | str, *, batch_size: int = 500) -> ImportResult:
    """Import one named TXT into locally installed Medallio tables.

    A changed historical prefix raises before writes commit. This avoids counting
    an edited visit twice while preserving already loaded fixed facts. A ruleset
    change creates another event version from existing messages, with views
    selecting only the current version.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    file_sha = _sha256(source)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('medallio.conversations.import'))")
            cur.execute("""
                INSERT INTO etl_control.conversation_sources(source_name)
                VALUES (%s) ON CONFLICT (source_name) DO NOTHING
            """, (source.name,))
            cur.execute("""
                SELECT source_id, last_file_sha256, message_count, current_ruleset_version
                FROM etl_control.conversation_sources WHERE source_name=%s FOR UPDATE
            """, (source.name,))
            source_id, old_sha, old_count, old_ruleset = cur.fetchone()
            if file_sha == old_sha and RULESET_VERSION == old_ruleset:
                return ImportResult(source.name, "UNCHANGED", old_count, 0, 0, None)

            messages = parse_export(source)
            cur.execute("""
                SELECT message_id FROM raw_conversations.messages
                WHERE source_id=%s ORDER BY ordinal
            """, (source_id,))
            old_ids = [record[0].strip() for record in cur.fetchall()]
            if len(old_ids) != old_count:
                raise RuntimeError("La cantidad histórica del control no coincide con RAW.")
            new_messages = validate_append_only(messages, old_ids)
            reclassify = RULESET_VERSION != old_ruleset
            to_extract = messages if reclassify else new_messages
            # Contextual reactions may refer to a sale in the previously loaded
            # prefix. Analyze the full sequence, then retain events belonging
            # to new messages on ordinary incremental imports.
            all_events = extract_linked_events(messages)
            new_ids = {message.message_id for message in to_extract}
            events = [event for event in all_events if event.message_id in new_ids]
            cur.execute("""
                INSERT INTO etl_control.conversation_import_runs
                    (source_id,file_sha256,parsed_messages,new_messages,new_events,ruleset_version)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING run_id
            """, (source_id, file_sha, len(messages), len(new_messages), len(events), RULESET_VERSION))
            run_id = cur.fetchone()[0]

            for chunk in _chunks(new_messages, batch_size):
                cur.executemany("""
                    INSERT INTO raw_conversations.messages
                        (message_id,source_id,ordinal,sent_at,sender,body,source_line,raw_message,is_multimedia,first_run_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, [(m.message_id, source_id, m.ordinal, m.sent_at, m.sender, m.body,
                          m.source_line, m.raw_message, m.is_multimedia, run_id) for m in chunk])
            for chunk in _chunks(events, batch_size):
                cur.executemany("""
                    INSERT INTO analytics.conversation_events
                        (event_id,message_id,source_id,event_index,ruleset_version,event_type,
                         reported_date,project_name,venue_type,count_min,count_max,confidence,
                         review_required,note,first_run_id,unit_code,related_event_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, [(e.event_id,e.message_id,source_id,e.event_index,e.ruleset_version,
                          e.event_type,e.reported_date,e.project_name,e.venue_type,e.count_min,
                          e.count_max,e.confidence,e.review_required,e.note,run_id,
                          e.unit_code,e.related_event_id) for e in chunk])
            cur.execute("""
                UPDATE etl_control.conversation_sources
                SET last_file_sha256=%s, message_count=%s, current_ruleset_version=%s,
                    last_success_at=now(), last_run_id=%s
                WHERE source_id=%s
            """, (file_sha,len(messages),RULESET_VERSION,run_id,source_id))
    return ImportResult(source.name, "IMPORTED", len(messages), len(new_messages), len(events), run_id)
