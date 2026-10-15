"""WhatsApp TXT parser. Message IDs remain stable when an export grows at the end."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


HEADER = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(?P<time>\d{1,2}:\d{2})(?:\s*(?P<ampm>[ap]\.?\s*m\.?))?"
    r"\s*-\s*(?P<content>.*)$", re.IGNORECASE,
)
SENDER = re.compile(r"^(?P<sender>[^:\n]{1,120}(?:\n[^:\n]{1,100})?):\s*(?P<body>[\s\S]*)$")


@dataclass(frozen=True)
class Message:
    message_id: str
    ordinal: int
    sent_at: datetime
    sender: str | None
    body: str
    source_line: int
    raw_message: str
    is_multimedia: bool


def _datetime(date: str, hour: str, ampm: str | None) -> datetime:
    day, month, year = (int(part) for part in date.split("/"))
    if year < 100:
        year += 2000
    hh, minute = (int(part) for part in hour.split(":"))
    if ampm:
        marker = re.sub(r"[^apm]", "", ampm.casefold())
        if not 1 <= hh <= 12:
            raise ValueError(f"Invalid 12-hour clock: {hour}")
        hh = hh % 12 + (12 if marker.startswith("p") else 0)
    return datetime(year, month, day, hh, minute)


def parse_export(path: Path | str) -> list[Message]:
    """Parse multiline messages and retain the source line for private review.

    A repeated, identical message gets its own ID through an occurrence index.
    IDs remain stable under append-only re-exports; historical changes are rejected
    by the import service before any insert.
    """
    result: list[Message] = []
    occurrences: dict[str, int] = defaultdict(int)
    current: tuple[datetime, int, list[str]] | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        sent_at, source_line, lines = current
        raw = "\n".join(lines)
        content = HEADER.match(lines[0]).group("content")  # type: ignore[union-attr]
        if len(lines) > 1:
            content += "\n" + "\n".join(lines[1:])
        sender_match = SENDER.match(content)
        sender = " ".join(sender_match.group("sender").split()) if sender_match else None
        body = sender_match.group("body") if sender_match else content
        canonical = f"{sent_at.isoformat()}\x1f{sender or ''}\x1f{' '.join(body.split())}"
        occurrences[canonical] += 1
        message_id = hashlib.sha256(f"{canonical}\x1f{occurrences[canonical]}".encode()).hexdigest()
        multimedia = bool(re.search(r"<[^>]*(?:omitid|adjunt|multimedia|video|imagen)[^>]*>", body, re.I))
        result.append(Message(message_id, len(result) + 1, sent_at, sender, body,
                              source_line, raw, multimedia))
        current = None

    with Path(path).open(encoding="utf-8-sig", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.rstrip("\r\n")
            match = HEADER.match(line)
            if match:
                flush()
                current = (_datetime(match.group("date"), match.group("time"), match.group("ampm")),
                           line_number, [line])
            elif current is not None:
                current[2].append(line)
    flush()
    return result
