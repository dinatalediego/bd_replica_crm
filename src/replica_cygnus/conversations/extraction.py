"""Conservative, versioned rules for commercial signals in group messages."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta

from .parser import Message


# Increment when changing classification semantics. Previous evidence remains append-only.
RULESET_VERSION = 2
PROJECTS = {
    "alicanto": "Alicanto", "capadocia": "Capadocia", "fenix": "Fenix",
    "matera": "Matera", "mariategui": "Mariátegui", "modena": "Modena",
    "modeba": "Modena", "siialia": "Sialia",
    "napoles": "Torre Nápoles", "sialia": "Sialia", "tizon y bueno": "Tizón y Bueno",
    "tizon": "Tizón y Bueno", "tyb": "Tizón y Bueno", "urbanzen": "Urbanzen",
    "torre marsano": "Torre Marsano", "pumacahua": "Pumacahua",
}
COUNTED = re.compile(
    r"(?<!\w)(?P<low>\d{1,3}|una?|cero)\s*(?:[-–a]\s*(?P<high>\d{1,3}))?\s*"
    r"(?P<unit>visitas?|clientes|personas|atenciones?|tr[aá]nsitos?)\b", re.I,
)
REVERSED_COUNT = re.compile(
    r"\b(?:visitas?|clientes|personas|atenciones?)\s*[:=]\s*"
    r"(?P<low>\d{1,3})(?:\s*[-–a]\s*(?P<high>\d{1,3}))?\b", re.I,
)
ATTENDED_COUNT = re.compile(
    r"\b(?:unos?|unas?|aproximadamente|aprox\.?|casi)?\s*(?P<low>\d{1,3})\s*"
    r"(?:atend[ií]|atendi[oó]|atendimos|atendidos?)(?!\w)", re.I,
)
UNIT_CODE = re.compile(
    r"\b(?:dpto\.?|departamento|unidad)\s*[:.#-]*\s*"
    r"(?P<code>(?:[A-Z]\s*-?\s*)?\d{3,4})\b", re.I,
)
NO_VISITS = re.compile(r"\b(?:no\s+(?:llegaron|hubo|tuvimos)|sin)\s+(?:visitas?|clientes?|atenciones?)\b", re.I)
SALES = re.compile(r"\bseparaci[oó]n\b", re.I)
SALE_CONTEXT = re.compile(r"\b(?:dpto\.?|departamento|edificio|proyecto|unidad|precio|s/|\d{3,4}\b)", re.I)
CONGRATULATIONS = re.compile(r"\b(?:felicitaciones?|felicidades|buena|bravo|vamos|esooo|separaciones\s+m[aá]s)\b", re.I)


@dataclass(frozen=True)
class Event:
    event_id: str
    message_id: str
    event_index: int
    ruleset_version: int
    event_type: str
    reported_date: date
    project_name: str | None
    venue_type: str | None
    count_min: int | None
    count_max: int | None
    confidence: str
    review_required: bool
    note: str
    unit_code: str | None = None
    related_event_id: str | None = None


def _fold(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(ch))


def _projects(text: str) -> set[str]:
    folded = _fold(text)
    return {canonical for alias, canonical in PROJECTS.items()
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded)}


def _venue(text: str) -> str | None:
    if re.search(r"\bferia\b", text, re.I):
        return "feria"
    if re.search(r"\b(?:sala|caseta|showroom)\b", text, re.I):
        return "sala"
    if re.search(r"^\s*salida\b", text, re.I):
        return "sala_inferida"
    return None


def _reported_date(message: Message, line: str) -> tuple[date, str]:
    # The reference can be in either the local line or an opening report sentence.
    candidate = line if re.search(r"\bayer\b", line, re.I) else message.body[:120]
    if re.search(r"\bayer\b", candidate, re.I):
        return message.sent_at.date() - timedelta(days=1), "ayer"
    weekday_names = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
    folded = _fold(candidate)
    for target, name in enumerate(weekday_names):
        if re.search(rf"\b(?:el\s+)?{name}\b", folded):
            offset = (message.sent_at.weekday() - target) % 7
            return message.sent_at.date() - timedelta(days=offset), "dia_semana_revisar"
    return message.sent_at.date(), "fecha_mensaje"


def _number(value: str) -> int:
    return {"un": 1, "una": 1, "cero": 0}.get(value.casefold(), int(value) if value.isdigit() else 0)


def _unit_code(text: str) -> str | None:
    match = UNIT_CODE.search(_fold(text))
    return re.sub(r"[\s-]+", "", match.group("code")).upper() if match else None


def _visit_numbers(line: str, *, continuation: bool) -> list[tuple[int, int, int, int, str]]:
    """Return disjoint numeric spans; accept counts without project/venue evidence."""
    matches: list[tuple[int, int, int, int, str]] = []
    for pattern, reason in ((COUNTED, "unidad_explicita"),
                            (REVERSED_COUNT, "unidad_explicita"),
                            (ATTENDED_COUNT, "atenciones_explicitas")):
        for match in pattern.finditer(line):
            if any(match.start() < end and match.end() > start for start, end, *_ in matches):
                continue
            low = _number(match.group("low"))
            high = int(match.group("high")) if "high" in match.groupdict() and match.group("high") else low
            matches.append((match.start(), match.end(), min(low, high), max(low, high), reason))
    # "Nelly atendió 20 personas y Luis unas 14" has two independent counts.
    if matches:
        for match in re.finditer(
            r"\b[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}\s+(?:unos?|unas?|aprox(?:imadamente)?\.?)\s+"
            r"(?P<count>\d{1,3})\b", line, re.I,
        ):
            if any(match.start() < end and match.end() > start for start, end, *_ in matches):
                continue
            number = int(match.group("count"))
            matches.append((match.start(), match.end(), number, number,
                            "continuacion_atenciones_revisar"))
    # A continuation such as "Luis unas 14" after "Nelly atendió 20 personas".
    if continuation and not matches:
        continuation_match = re.search(r"\b(?:unos?|unas?|aprox(?:imadamente)?\.?)\s+(\d{1,3})\b", line, re.I)
        if continuation_match:
            number = int(continuation_match.group(1))
            matches.append((continuation_match.start(), continuation_match.end(), number, number,
                            "continuacion_atenciones_revisar"))
    return sorted(matches)


def extract_events(message: Message) -> list[Event]:
    body = message.body.strip()
    if not body or message.sender is None:
        return []
    found: list[tuple[str, date, str | None, str | None, int | None, int | None, str, bool, str]] = []
    all_projects = _projects(body)
    project = next(iter(all_projects)) if len(all_projects) == 1 else None
    venue = _venue(body)

    # One visit observation per segment. A 7 p.m. chat participant is never a visit.
    visit_continuation = False
    for line in body.splitlines():
        if re.search(r"\b(?:ca[ií]da|anulad[ao])\b", body[:100], re.I):
            break
        line_projects = _projects(line)
        line_project = next(iter(line_projects)) if len(line_projects) == 1 else project
        if len(line_projects) > 1:
            line_project = None
        visit_context = bool(re.search(r"\b(?:visitas?|atend[ií](?:mos|o|ó)?|atenciones?|tr[aá]nsitos?|salida)\b", line, re.I))
        candidates = _visit_numbers(line, continuation=visit_continuation)
        for start, end, lo, hi, match_reason in candidates:
            unit_text = _fold(line[start:end])
            if re.search(r"\b(?:clientes?|personas?)\b", unit_text) and not (visit_context or _venue(line) or venue or visit_continuation):
                continue
            if re.search(r"\b(?:dpto|departamento|precio|valor|m2|m²)\b", line[:start], re.I) and not visit_context:
                continue
            report_day, reason = _reported_date(message, line)
            line_venue = _venue(line) or venue
            uncertain = (hi != lo or line_project is None or line_venue not in {"sala", "feria"}
                         or len(all_projects) > 1 or reason == "dia_semana_revisar"
                         or match_reason == "continuacion_atenciones_revisar")
            found.append(("visita_reporte", report_day, line_project, line_venue, lo, hi,
                          "media" if not uncertain else "baja", uncertain,
                          f"{reason};{match_reason}"))
        if NO_VISITS.search(line) and not candidates:
            report_day, reason = _reported_date(message, line)
            line_venue = _venue(line) or venue
            found.append(("visita_reporte", report_day, line_project, line_venue, 0, 0,
                          "media", line_project is None or line_venue not in {"sala", "feria"}, reason))
        if candidates and (visit_context or "atenciones" in _fold(line)):
            visit_continuation = True

    if SALES.search(body) and SALE_CONTEXT.search(body) and not CONGRATULATIONS.search(body[:100]) \
            and not re.search(r"\b(?:ca[ií]da|anulad[ao]|separaci[oó]n\?|no\s+separaci[oó]n)\b", body[:120], re.I):
        found.append(("separacion_anuncio", message.sent_at.date(), project, venue,
                      None, None, "media", project is None or len(all_projects) > 1, "anuncio_chat_no_crm"))
    if re.search(r"\b(?:firm[oó]|firmada|firmado)\s+(?:la\s+)?minuta\b", body, re.I) \
            and not re.search(r"\b(?:no|sin|falta)\s+(?:firmar|firma)\s+minuta\b", body, re.I):
        found.append(("minuta_reporte", message.sent_at.date(), project, venue,
                      None, None, "media", True, "verificar_en_crm"))
    if re.search(r"\b(?:pago\s+(?:de\s+)?inicial|inicial\s+(?:dpto\.?|departamento|edificio))\b", body, re.I) \
            and not re.search(r"\b(?:pendiente|falta|no\s+pag[oó]|cuando)\b", body[:100], re.I):
        found.append(("pago_inicial_reporte", message.sent_at.date(), project, venue,
                      None, None, "media", True, "verificar_en_crm"))
    if re.search(r"\b(?:\d+|una?)\s+citas?\b", body, re.I) and not re.search(r"\b(?:por confirmar|no\s+llegaron)\b", body, re.I):
        found.append(("cita_reporte", message.sent_at.date(), project, venue,
                      None, None, "baja", True, "cita_no_equivale_a_visita"))
    if re.search(r"\b(?:bloquead[ao]s?|bloqueo|no\s+ofrecer)\b", body, re.I):
        found.append(("bloqueo_stock", message.sent_at.date(), project, venue,
                      None, None, "media", project is None, "senal_operativa"))
    if re.search(r"\b(?:sperant|error\s+en\s+(?:crm|sistema))\b", body, re.I):
        found.append(("incidencia_crm", message.sent_at.date(), project, venue,
                      None, None, "media", project is None, "senal_operativa"))
    if re.search(r"^\s*salida\b", body, re.I):
        found.append(("salida_sala", message.sent_at.date(), project, venue,
                      None, None, "media", project is None or venue == "sala_inferida", "reporte_cierre_sala"))
    if venue == "feria" and not any(e[0] in {"visita_reporte", "separacion_anuncio"} for e in found):
        found.append(("actividad_feria", message.sent_at.date(), project, venue,
                      None, None, "baja", True, "mencion_feria"))

    events = []
    for index, (kind, day, project_name, place, low, high, confidence, review, note) in enumerate(found, 1):
        event_id = hashlib.sha256(f"{message.message_id}|{RULESET_VERSION}|{index}".encode()).hexdigest()
        events.append(Event(event_id, message.message_id, index, RULESET_VERSION, kind, day,
                            project_name, place, low, high, confidence, review, note,
                            _unit_code(body) if kind == "separacion_anuncio" else None))
    return events


def _sender_named(sender: str | None, text: str) -> bool:
    if not sender:
        return False
    tokens = [token for token in _fold(sender).split() if len(token) >= 4]
    return bool(tokens and re.search(rf"(?<!\w){re.escape(tokens[0])}(?!\w)", _fold(text)))


def extract_linked_events(messages: list[Message]) -> list[Event]:
    """Versioned batch extraction; link congratulations only to preceding sales."""
    result: list[Event] = []
    recent_sales: deque[tuple[Message, Event]] = deque()
    for message in messages:
        current = extract_events(message)
        body = message.body.strip()
        while recent_sales and message.sent_at - recent_sales[0][0].sent_at > timedelta(hours=24):
            recent_sales.popleft()
        if message.sender and len(body) < 350 and CONGRATULATIONS.search(body[:100]) \
                and not any(event.event_type == "separacion_anuncio" for event in current):
            project_names = _projects(body)
            unit = _unit_code(body)
            matches: list[tuple[Message, Event, bool]] = []
            for sale_message, sale_event in reversed(recent_sales):
                if sale_message.sender == message.sender or sale_message.sent_at > message.sent_at:
                    continue
                person_match = _sender_named(sale_message.sender, body)
                project_match = bool(sale_event.project_name and sale_event.project_name in project_names)
                unit_match = bool(unit and sale_event.unit_code and unit == sale_event.unit_code)
                if project_names and not project_match or unit and sale_event.unit_code and not unit_match:
                    continue
                explicit = person_match or project_match or unit_match
                if explicit or message.sent_at - sale_message.sent_at <= timedelta(minutes=15):
                    matches.append((sale_message, sale_event, explicit))
            explicit_matches = [match for match in matches if match[2]]
            if explicit_matches:
                matches = explicit_matches
            elif len(matches) != 1:
                matches = []  # Unqualified reaction and multiple candidate sales.
            if matches:
                sale_message, sale_event, explicit = matches[0]
                index = len(current) + 1
                event_id = hashlib.sha256(
                    f"{message.message_id}|{RULESET_VERSION}|{index}".encode()).hexdigest()
                current.append(Event(
                    event_id, message.message_id, index, RULESET_VERSION, "celebracion",
                    message.sent_at.date(), sale_event.project_name, None, None, None,
                    "media" if explicit and len(matches) == 1 else "baja",
                    not explicit or len(matches) > 1,
                    "reaccion_vinculada_24h" if explicit else "reaccion_proxima_15m",
                    sale_event.unit_code, sale_event.event_id,
                ))
        result.extend(current)
        for event in current:
            if event.event_type == "separacion_anuncio":
                recent_sales.append((message, event))
    return result
