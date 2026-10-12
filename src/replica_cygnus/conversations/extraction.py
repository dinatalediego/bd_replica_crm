"""Conservative, versioned rules for commercial signals in group messages."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from .parser import Message


# Increment when changing classification semantics. Previous evidence remains append-only.
RULESET_VERSION = 1
PROJECTS = {
    "alicanto": "Alicanto", "capadocia": "Capadocia", "fenix": "Fenix",
    "matera": "Matera", "mariategui": "Mariátegui", "modena": "Modena",
    "napoles": "Torre Nápoles", "sialia": "Sialia", "tizon y bueno": "Tizón y Bueno",
    "tizon": "Tizón y Bueno", "tyb": "Tizón y Bueno", "urbanzen": "Urbanzen",
    "torre marsano": "Torre Marsano", "pumacahua": "Pumacahua",
}
COUNTED = re.compile(
    r"(?<!\w)(?P<low>\d{1,3}|una?|cero)\s*(?:[-–a]\s*(?P<high>\d{1,3}))?\s*"
    r"(?P<unit>visitas?|clientes|personas|atenciones?|tr[aá]nsitos?)\b", re.I,
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


def extract_events(message: Message) -> list[Event]:
    body = message.body.strip()
    if not body or message.sender is None:
        return []
    found: list[tuple[str, date, str | None, str | None, int | None, int | None, str, bool, str]] = []
    all_projects = _projects(body)
    project = next(iter(all_projects)) if len(all_projects) == 1 else None
    venue = _venue(body)

    # One visit observation per segment. A 7 p.m. chat participant is never a visit.
    for line in body.splitlines():
        if re.search(r"\b(?:ca[ií]da|anulad[ao])\b", body[:100], re.I):
            break
        line_projects = _projects(line)
        line_project = next(iter(line_projects)) if len(line_projects) == 1 else project
        if len(line_projects) > 1:
            line_project = None
        visit_context = bool(re.search(r"\b(?:visitas?|atend[ií](?:mos|o|ó)?|atenciones?|tr[aá]nsitos?|salida)\b", line, re.I))
        for match in COUNTED.finditer(line):
            unit = _fold(match.group("unit"))
            if unit.startswith(("cliente", "persona")) and not (visit_context or _venue(line) or venue):
                continue
            if re.search(r"\b(?:dpto|departamento|precio|valor|m2|m²)\b", line[:match.start()], re.I) and not visit_context:
                continue
            lo = _number(match.group("low"))
            hi = int(match.group("high")) if match.group("high") else lo
            if hi < lo:
                lo, hi = hi, lo
            report_day, reason = _reported_date(message, line)
            line_venue = _venue(line) or venue
            uncertain = (hi != lo or line_project is None or line_venue not in {"sala", "feria"}
                         or len(all_projects) > 1 or reason == "dia_semana_revisar")
            found.append(("visita_reporte", report_day, line_project, line_venue, lo, hi,
                          "media" if not uncertain else "baja", uncertain, reason))
        if NO_VISITS.search(line) and not COUNTED.search(line):
            report_day, reason = _reported_date(message, line)
            line_venue = _venue(line) or venue
            found.append(("visita_reporte", report_day, line_project, line_venue, 0, 0,
                          "media", line_project is None or line_venue not in {"sala", "feria"}, reason))

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
    if CONGRATULATIONS.search(body[:100]) and len(body) < 350:
        found.append(("celebracion", message.sent_at.date(), project, venue,
                      None, None, "media", False, "reaccion_social"))
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
                            project_name, place, low, high, confidence, review, note))
    return events
