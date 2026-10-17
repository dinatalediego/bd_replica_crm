"""Sanitized Medallio -> Medallio Pocket export helpers.

The mobile boundary is intentionally narrow: project-month aggregates only.
No CRM entity identifiers or customer free text are accepted by this module.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable


SOURCE_FIELDS = (
    "periodo_mes",
    "codigo_proyecto",
    "nombre_proyecto",
    "primera_fecha_observada",
    "ultima_fecha_observada",
    "stock_inicial",
    "altas_mes",
    "separaciones_brutas_mes",
    "caidas_mes",
    "separaciones_netas_mes",
    "ventas_minutas_mes",
    "stock_final",
    "absorcion_bruta_mes",
    "absorcion_neta_mes",
    "absorcion_neta_6m",
    "stock_disponible_actual",
    "cobertura_stock_disponible_ratio",
    "ledger_reconcilia_estado_actual",
    "calidad_stock_historico",
    "metodo_stock_historico",
    "metodo_movimiento",
    "metodo_venta",
    "mes_parcial",
    "fecha_corte",
)

FORBIDDEN_FIELD_RE = re.compile(
    r"(cliente|client|lead|dni|document|telefono|phone|celular|correo|email|"
    r"direccion|address|nota|note|coment|conversation|grabacion|recording|"
    r"proforma|unidad|asesor)",
    re.IGNORECASE,
)
EMAIL_LIKE_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
PHONE_LIKE_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")


@dataclass(frozen=True)
class PocketCommercialRow:
    project_ref: str
    project_name: str
    period_month: date
    source_cutoff: date
    is_partial: bool
    stock_open: int
    gross_separations: int
    falls: int
    net_separations: int
    sales_minutas: int
    stock_close: int
    gross_absorption: Decimal | None
    net_absorption: Decimal | None
    net_absorption_6m: Decimal | None
    current_stock: int | None
    stock_coverage: Decimal | None
    current_state_reconciled: bool | None
    quality_status: str

    def as_db_tuple(self) -> tuple[Any, ...]:
        return (
            self.project_ref,
            self.project_name,
            self.period_month,
            self.source_cutoff,
            self.is_partial,
            self.stock_open,
            self.gross_separations,
            self.falls,
            self.net_separations,
            self.sales_minutas,
            self.stock_close,
            self.gross_absorption,
            self.net_absorption,
            self.net_absorption_6m,
            self.current_stock,
            self.stock_coverage,
            self.current_state_reconciled,
            self.quality_status,
        )


def assert_source_contract(columns: Iterable[str]) -> None:
    columns = tuple(columns)
    if set(columns) != set(SOURCE_FIELDS):
        missing = sorted(set(SOURCE_FIELDS) - set(columns))
        extra = sorted(set(columns) - set(SOURCE_FIELDS))
        raise ValueError(f"Unexpected Pocket source columns; missing={missing}, extra={extra}")
    forbidden = [name for name in columns if FORBIDDEN_FIELD_RE.search(name)]
    if forbidden:
        raise ValueError(f"Forbidden fields in Pocket source: {forbidden}")


def project_ref(project_code: str, secret: bytes) -> str:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("POCKET_PROJECT_HMAC_KEY must encode at least 32 bytes")
    if not isinstance(project_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", project_code):
        raise ValueError("Invalid project code")
    return hmac.new(secret, project_code.encode("utf-8"), hashlib.sha256).hexdigest()


def _clean_project_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid project name")
    text = " ".join(value.split()).strip()
    if not 1 <= len(text) <= 160:
        raise ValueError("Invalid project name length")
    if EMAIL_LIKE_RE.search(text) or PHONE_LIKE_RE.search(text):
        raise ValueError("Project name contains PII-like content")
    return text


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Invalid {field}")
    number = int(value)
    if number < 0 or Decimal(str(value)) != Decimal(number):
        raise ValueError(f"Invalid {field}")
    return number


def _optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, field)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def transform_source_row(source: dict[str, Any], secret: bytes) -> PocketCommercialRow:
    assert_source_contract(source.keys())

    month = source["periodo_mes"]
    cutoff = source["fecha_corte"]
    if not isinstance(month, date) or not isinstance(cutoff, date):
        raise ValueError("Invalid dates")
    if month.day != 1 or cutoff < month:
        raise ValueError("Invalid monthly cut")

    partial = source["mes_parcial"]
    if not isinstance(partial, bool):
        raise ValueError("Invalid mes_parcial")

    quality = source["calidad_stock_historico"]
    if not isinstance(quality, str) or quality not in {
        "CERTIFICADO_ESTADO_ACTUAL",
        "HISTORICO_LEDGER_CON_GAP_DE_COBERTURA",
    }:
        raise ValueError("Unexpected stock quality status")

    reconciled = source["ledger_reconcilia_estado_actual"]
    if reconciled is not None and not isinstance(reconciled, bool):
        raise ValueError("Invalid reconciliation flag")

    return PocketCommercialRow(
        project_ref=project_ref(source["codigo_proyecto"], secret),
        project_name=_clean_project_name(source["nombre_proyecto"]),
        period_month=month,
        source_cutoff=cutoff,
        is_partial=partial,
        stock_open=_nonnegative_int(source["stock_inicial"], "stock_inicial"),
        gross_separations=_nonnegative_int(source["separaciones_brutas_mes"], "separaciones_brutas_mes"),
        falls=_nonnegative_int(source["caidas_mes"], "caidas_mes"),
        net_separations=int(source["separaciones_netas_mes"]),
        sales_minutas=_nonnegative_int(source["ventas_minutas_mes"], "ventas_minutas_mes"),
        stock_close=_nonnegative_int(source["stock_final"], "stock_final"),
        gross_absorption=_decimal(source["absorcion_bruta_mes"]),
        net_absorption=_decimal(source["absorcion_neta_mes"]),
        net_absorption_6m=_decimal(source["absorcion_neta_6m"]),
        current_stock=_optional_nonnegative_int(source["stock_disponible_actual"], "stock_disponible_actual"),
        stock_coverage=_decimal(source["cobertura_stock_disponible_ratio"]),
        current_state_reconciled=reconciled,
        quality_status=quality,
    )


def build_rows(source_rows: list[dict[str, Any]], secret: bytes) -> list[PocketCommercialRow]:
    if not source_rows:
        raise ValueError("Pocket export requires at least one commercial row")
    rows = [transform_source_row(row, secret) for row in source_rows]
    keys = [(row.project_ref, row.period_month) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate project-month in Pocket export")
    return rows


def health_score(row: PocketCommercialRow) -> int:
    coverage = float(row.stock_coverage) if row.stock_coverage is not None else 0.0
    score = 45
    if row.current_state_reconciled:
        score += 30
    if coverage >= 0.95:
        score += 20
    elif coverage >= 0.80:
        score += 10
    if not row.is_partial:
        score += 5
    return max(0, min(100, score))


def latest_rows(rows: list[PocketCommercialRow]) -> list[PocketCommercialRow]:
    latest: dict[str, PocketCommercialRow] = {}
    for row in rows:
        current = latest.get(row.project_ref)
        if current is None or row.period_month > current.period_month:
            latest[row.project_ref] = row
    return sorted(latest.values(), key=lambda x: x.project_name.casefold())
