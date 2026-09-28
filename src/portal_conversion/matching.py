from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

EMPTY_TOKENS = {"", "-", "none", "null", "nan", "n/a"}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in EMPTY_TOKENS else text


def normalize_source_document(value: Any) -> str:
    """Stable source key. AUTO-* remains an identifier, never a DNI."""
    text = _as_text(value).lower()
    if text.endswith(".0") and re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\s+", "", text)


def normalize_dni(value: Any) -> str:
    """DNI is valid only when the raw value itself is exactly eight digits."""
    text = _as_text(value)
    if text.endswith(".0") and re.fullmatch(r"\d{8}\.0", text):
        text = text[:-2]
    return text if re.fullmatch(r"\d{8}", text) else ""


def normalize_text(value: Any) -> str:
    text = _as_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(value: Any) -> str:
    return normalize_text(value)


def canonical_name(value: Any) -> str:
    tokens = [token for token in normalize_name(value).split() if len(token) > 1]
    return " ".join(sorted(tokens))


def normalize_email(value: Any) -> str:
    text = _as_text(value).lower().replace(" ", "")
    if not text or text.count("@") != 1:
        return ""
    local, domain = text.split("@", 1)
    if not local or "." not in domain:
        return ""
    return text


def normalize_phone(value: Any) -> str:
    raw = _as_text(value)
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) >= 11 and digits[-11:-9] == "51" and len(digits[-9:]) == 9:
        return digits[-9:]
    if len(digits) == 9:
        return digits
    return digits[-15:]


def _sequence_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(100.0 * SequenceMatcher(None, a, b).ratio(), 2)


def name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_norm = normalize_name(a)
    b_norm = normalize_name(b)
    a_can = canonical_name(a_norm)
    b_can = canonical_name(b_norm)
    seq = _sequence_score(a_norm, b_norm)
    token_seq = _sequence_score(a_can, b_can)
    a_tokens = set(a_can.split())
    b_tokens = set(b_can.split())
    jaccard = 100.0 * len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return round(max(seq, token_seq, jaccard), 2)


def email_similarity(a: str, b: str) -> float:
    a_norm = normalize_email(a)
    b_norm = normalize_email(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 100.0
    a_local, a_domain = a_norm.split("@", 1)
    b_local, b_domain = b_norm.split("@", 1)
    score = _sequence_score(a_norm, b_norm)
    if a_domain != b_domain:
        score = min(score, 92.0)
    if a_domain == b_domain:
        score = max(score, 0.8 * _sequence_score(a_local, b_local) + 20.0)
    return round(min(score, 100.0), 2)


def phone_similarity(a: str, b: str) -> float:
    a_norm = normalize_phone(a)
    b_norm = normalize_phone(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 100.0
    if len(a_norm) >= 7 and len(b_norm) >= 7 and a_norm[-7:] == b_norm[-7:]:
        return 96.0
    return _sequence_score(a_norm, b_norm)


@dataclass(frozen=True)
class PersonIdentity:
    source_document: str
    dni: str
    name: str
    phone: str
    email: str

    @classmethod
    def build(
        cls,
        *,
        source_document: Any = None,
        dni: Any = None,
        name: Any = None,
        phone: Any = None,
        email: Any = None,
    ) -> "PersonIdentity":
        raw_document = source_document if source_document is not None else dni
        return cls(
            source_document=normalize_source_document(raw_document),
            dni=normalize_dni(dni if dni is not None else raw_document),
            name=normalize_name(name),
            phone=normalize_phone(phone),
            email=normalize_email(email),
        )

    def strong_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        if self.dni:
            keys.append(f"dni:{self.dni}")
        if self.source_document:
            keys.append(f"doc:{self.source_document}")
        name_key = canonical_name(self.name)
        if self.email and self.phone:
            keys.append(f"email_phone:{self.email}|{self.phone}")
        if self.email and name_key:
            keys.append(f"email_name:{self.email}|{name_key}")
        if self.phone and name_key:
            keys.append(f"phone_name:{self.phone}|{name_key}")
        return tuple(dict.fromkeys(keys))

    def preferred_person_key(self) -> str:
        if self.dni:
            return f"dni:{self.dni}"
        if self.email and self.phone:
            return f"email_phone:{self.email}|{self.phone}"
        if self.email:
            return f"email:{self.email}"
        if self.phone:
            return f"phone:{self.phone}"
        if self.source_document:
            return f"doc:{self.source_document}"
        if self.name:
            return f"name:{canonical_name(self.name)}"
        return ""


@dataclass(frozen=True)
class MatchResult:
    status: str
    criteria: str
    global_score: float
    dni_score: float
    name_score: float
    phone_score: float
    email_score: float

    @property
    def automatic_conversion(self) -> bool:
        return self.status in {"CONFIRMADO", "PROBABLE"}


STATUS_RANK = {"NO MATCH": 0, "REVISAR": 1, "PROBABLE": 2, "CONFIRMADO": 3}


def score_match(lead: PersonIdentity, buyer: PersonIdentity) -> MatchResult:
    dni_score = 100.0 if lead.dni and buyer.dni and lead.dni == buyer.dni else 0.0
    name_score = name_similarity(lead.name, buyer.name)
    phone_score = phone_similarity(lead.phone, buyer.phone)
    email_score = email_similarity(lead.email, buyer.email)

    if dni_score == 100.0:
        return MatchResult(
            "CONFIRMADO", "DNI exacto (8 dígitos)", 100.0,
            dni_score, name_score, phone_score, email_score,
        )

    contacts = sorted([phone_score, email_score], reverse=True)
    global_score = round(0.45 * contacts[0] + 0.30 * contacts[1] + 0.25 * name_score, 2)

    if email_score >= 99 and phone_score >= 99:
        status, criteria = "CONFIRMADO", "Email + celular exactos/casi exactos"
        global_score = max(global_score, 99.0)
    elif name_score >= 92 and (email_score >= 99 or phone_score >= 99):
        status, criteria = "CONFIRMADO", "Nombre + contacto exacto/casi exacto"
        global_score = max(global_score, 97.0)
    elif (name_score >= 88 and max(email_score, phone_score) >= 94) or (
        email_score >= 97 and phone_score >= 94
    ):
        status, criteria = "PROBABLE", "Dos evidencias consistentes"
        global_score = max(global_score, 90.0)
    elif name_score >= 82 and max(email_score, phone_score) >= 88:
        status, criteria = "REVISAR", "Coincidencia parcial corroborada"
        global_score = max(global_score, 80.0)
    else:
        status, criteria = "NO MATCH", "Sin evidencia suficiente"

    return MatchResult(
        status, criteria, round(global_score, 2),
        dni_score, name_score, phone_score, email_score,
    )


def best_result(results: Iterable[tuple[str, MatchResult]]) -> tuple[str, MatchResult] | None:
    ranked = list(results)
    if not ranked:
        return None
    ranked.sort(
        key=lambda item: (
            STATUS_RANK.get(item[1].status, 0),
            item[1].global_score,
            item[1].dni_score,
            max(item[1].email_score, item[1].phone_score),
            item[1].name_score,
        ),
        reverse=True,
    )
    return ranked[0]
