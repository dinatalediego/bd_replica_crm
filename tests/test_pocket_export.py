from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from replica_cygnus.pocket_export import (
    SOURCE_FIELDS,
    assert_source_contract,
    build_rows,
    health_score,
    latest_rows,
    transform_source_row,
)


SECRET = b"0123456789abcdef0123456789abcdef"


def source_row(**overrides):
    row = {
        "periodo_mes": date(2026, 9, 1),
        "codigo_proyecto": "NP",
        "nombre_proyecto": "Torre Napoles",
        "primera_fecha_observada": date(2026, 9, 1),
        "ultima_fecha_observada": date(2026, 9, 30),
        "stock_inicial": 40,
        "altas_mes": 0,
        "separaciones_brutas_mes": 5,
        "caidas_mes": 1,
        "separaciones_netas_mes": 4,
        "ventas_minutas_mes": 3,
        "stock_final": 33,
        "absorcion_bruta_mes": Decimal("0.125"),
        "absorcion_neta_mes": Decimal("0.10"),
        "absorcion_neta_6m": Decimal("0.48"),
        "stock_disponible_actual": 13,
        "cobertura_stock_disponible_ratio": Decimal("1.0"),
        "ledger_reconcilia_estado_actual": True,
        "calidad_stock_historico": "CERTIFICADO_ESTADO_ACTUAL",
        "metodo_stock_historico": "OBSERVADO_LEDGER",
        "metodo_movimiento": "SEPARACIONES_EFECTIVAS_MENOS_CAIDAS",
        "metodo_venta": "VENTA_EFECTIVA / MINUTA_CANONICA",
        "mes_parcial": False,
        "fecha_corte": date(2026, 10, 17),
    }
    row.update(overrides)
    return row


def test_source_contract_is_exact_and_has_no_pii_fields():
    assert_source_contract(SOURCE_FIELDS)
    assert not any(
        bad in name.lower()
        for name in SOURCE_FIELDS
        for bad in ("cliente", "lead", "dni", "telefono", "correo", "email", "proforma", "unidad")
    )


def test_transform_hashes_project_code_and_keeps_only_business_name():
    out = transform_source_row(source_row(), SECRET)
    assert out.project_name == "Torre Napoles"
    assert out.project_ref != "NP"
    assert len(out.project_ref) == 64
    assert out.sales_minutas == 3
    assert out.net_absorption == Decimal("0.10")


def test_project_name_rejects_email_like_content():
    with pytest.raises(ValueError, match="PII-like"):
        transform_source_row(source_row(nombre_proyecto="Proyecto cliente@empresa.com"), SECRET)


def test_extra_source_field_fails_closed():
    row = source_row(cliente_nombre="Persona")
    with pytest.raises(ValueError, match="Unexpected Pocket source columns"):
        transform_source_row(row, SECRET)


def test_duplicate_project_month_fails():
    with pytest.raises(ValueError, match="Duplicate project-month"):
        build_rows([source_row(), source_row()], SECRET)


def test_latest_rows_uses_most_recent_month():
    older = transform_source_row(source_row(), SECRET)
    newer = transform_source_row(
        source_row(
            periodo_mes=date(2026, 10, 1),
            stock_inicial=33,
            stock_final=28,
            stock_disponible_actual=12,
            mes_parcial=True,
        ),
        SECRET,
    )
    latest = latest_rows([older, newer])
    assert len(latest) == 1
    assert latest[0].period_month == date(2026, 10, 1)


def test_health_score_rewards_reconciliation_and_coverage():
    row = transform_source_row(source_row(), SECRET)
    assert health_score(row) == 100
