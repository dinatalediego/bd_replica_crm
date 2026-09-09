from datetime import date

from replica_cygnus.monthly_stock_export.service import (
    _money_format,
    _period_start,
    _safe_sheet_name,
)


def test_period_start_from_text():
    assert _period_start("2026-09") == date(2026, 9, 1)


def test_period_start_from_date_normalizes_day():
    assert _period_start(date(2026, 9, 19)) == date(2026, 9, 1)


def test_safe_sheet_name_removes_excel_forbidden_chars():
    value = _safe_sheet_name("TIZÓN / BUENO:*?")
    assert all(char not in value for char in "[]:*?/\\")
    assert len(value) <= 31


def test_money_format_pen_uses_soles_prefix():
    assert _money_format("PEN") == '"S/ "#,##0.00'
