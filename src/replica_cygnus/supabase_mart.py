"""Allowlisted local monthly aggregates for a private Supabase modeling pilot."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import date


SOURCE_FIELDS = (
    "codigo_proyecto", "periodo_mes", "mes_vida", "mes_calendario", "fecha_corte",
    "mes_parcial", "stock_inicial", "ventas_mes", "stock_final", "dias_exposicion",
    "unidades_revision",
)
TARGET_FIELDS = (
    "project_ref", "period_month", "life_month", "calendar_month", "source_cutoff",
    "is_partial", "stock_open", "sales_units", "stock_close", "exposure_days",
    "review_units", "source_hash", "data_origin",
)


def content_hash(row: dict) -> str:
    # A refreshed cutoff without changed business facts is not a data revision.
    content = {key: value for key, value in row.items() if key not in ("source_hash", "source_cutoff")}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _day(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"Invalid {field}")


def _count(value: object, field: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"Invalid {field}")
    return value


def transform(source: dict, secret: bytes, *, origin: str = "MEDALLIO_AGGREGATE") -> dict:
    """Fail closed on unknown source fields; never export a project name or raw row."""
    if not isinstance(source, dict) or set(source) != set(SOURCE_FIELDS):
        raise ValueError("Unexpected source columns")
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("HMAC key must be at least 32 bytes")
    if origin not in ("MEDALLIO_AGGREGATE", "SYNTHETIC"):
        raise ValueError("Invalid data origin")
    code = source["codigo_proyecto"]
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", code):
        raise ValueError("Invalid local project code")
    month = _day(source["periodo_mes"], "periodo_mes")
    cutoff = _day(source["fecha_corte"], "fecha_corte")
    if month.day != 1 or cutoff < month:
        raise ValueError("Invalid monthly cut")
    partial = source["mes_parcial"]
    if not isinstance(partial, bool):
        raise ValueError("Invalid mes_parcial")
    life = _count(source["mes_vida"], "mes_vida", minimum=1)
    calendar = _count(source["mes_calendario"], "mes_calendario", minimum=1)
    if calendar != month.month:
        raise ValueError("Calendar mismatch")
    stock = _count(source["stock_inicial"], "stock_inicial")
    sales = _count(source["ventas_mes"], "ventas_mes")
    close = _count(source["stock_final"], "stock_final")
    if stock - sales != close:
        raise ValueError("Stock reconciliation failed")
    result = {
        "project_ref": hmac.new(secret, code.encode(), hashlib.sha256).hexdigest(),
        "period_month": month.isoformat(),
        "life_month": life,
        "calendar_month": calendar,
        "source_cutoff": cutoff.isoformat(),
        "is_partial": partial,
        "stock_open": stock,
        "sales_units": sales,
        "stock_close": close,
        "exposure_days": _count(source["dias_exposicion"], "dias_exposicion"),
        "review_units": _count(source["unidades_revision"], "unidades_revision"),
        "data_origin": origin,
    }
    result["source_hash"] = content_hash(result)
    return result


def build_packet(source_rows: list[dict], secret: bytes, *, origin: str = "MEDALLIO_AGGREGATE") -> dict:
    if not isinstance(source_rows, list) or not 1 <= len(source_rows) <= 1000:
        raise ValueError("Pilot requires 1–1000 monthly rows")
    rows = [transform(row, secret, origin=origin) for row in source_rows]
    keys = [(row["project_ref"], row["period_month"]) for row in rows]
    if len(set(keys)) != len(keys) or len({row["project_ref"] for row in rows}) > 3:
        raise ValueError("Duplicate month or too many projects")
    return {"packet_version": 1, "source_relation": "analytics.comercial_proyecto_mes", "rows": rows}


def validate_packet(packet: dict) -> list[dict]:
    if not isinstance(packet, dict) or set(packet) != {"packet_version", "source_relation", "rows"}:
        raise ValueError("Unexpected packet")
    if packet["packet_version"] != 1 or packet["source_relation"] != "analytics.comercial_proyecto_mes":
        raise ValueError("Unexpected packet version or source")
    rows = packet["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000 or len(json.dumps(packet)) > 700000:
        raise ValueError("Packet too large")
    keys = set()
    projects = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(TARGET_FIELDS):
            raise ValueError("Unknown target field")
        ref = row["project_ref"]
        digest = row["source_hash"]
        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}", ref):
            raise ValueError("Invalid project reference")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid source hash")
        expected = content_hash(row)
        if digest != expected:
            raise ValueError("Tampered aggregate")
        month = _day(row["period_month"], "period_month")
        cutoff = _day(row["source_cutoff"], "source_cutoff")
        calendar = _count(row["calendar_month"], "calendar_month", minimum=1)
        if month.day != 1 or cutoff < month or calendar != month.month:
            raise ValueError("Invalid monthly cut")
        if not isinstance(row["is_partial"], bool) or row["data_origin"] not in ("MEDALLIO_AGGREGATE", "SYNTHETIC"):
            raise ValueError("Invalid metadata")
        for name in ("life_month", "stock_open", "sales_units", "stock_close", "exposure_days", "review_units"):
            _count(row[name], name, minimum=1 if name == "life_month" else 0)
        if row["stock_open"] - row["sales_units"] != row["stock_close"]:
            raise ValueError("Stock reconciliation failed")
        key = (ref, month)
        if key in keys:
            raise ValueError("Duplicate project month")
        keys.add(key)
        projects.add(ref)
    if len(projects) > 3:
        raise ValueError("Too many projects")
    return rows
