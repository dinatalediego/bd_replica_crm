from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_b_installs_conversion_evidence_quality_contract() -> None:
    install_py = (ROOT / "src" / "absorption_phase_b" / "install.py").read_text(encoding="utf-8")
    assert '"03b_sale_date_pago_ci.sql"' in install_py
    assert '"03c_pago_ci_quality_override.sql"' in install_py
    assert install_py.index('"03b_sale_date_pago_ci.sql"') < install_py.index('"03c_pago_ci_quality_override.sql"')


def test_fecha_de_minuta_is_the_dated_parse_gate() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "fecha_pago_ci_parse_error" in normalized
    assert "fecha_de_minuta" in normalized
    assert "business_alias','fecha_pagoci_pm'" in normalized
    assert "try_parse_business_date" in normalized


def test_pago_ci_is_a_marker_not_a_date() -> None:
    correction = (ROOT / "sql" / "20_absorption_phase_b" / "03b_sale_date_pago_ci.sql").read_text(encoding="utf-8")
    qa = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(encoding="utf-8")
    normalized_correction = " ".join(correction.lower().split())
    normalized_qa = " ".join(qa.lower().split())

    # Assert semantic evidence rather than depending on one exact comment phrase.
    assert "pago_ci" in normalized_correction
    assert "marker" in normalized_correction
    assert "not the dated conversion source" in normalized_correction
    assert "pagó cuota inicial (minuta)" in normalized_qa
    assert "pago_ci_unknown_marker_value" in normalized_qa
    assert "pago_ci_marker_without_fecha_pago_ci" in normalized_qa
    assert "fecha_pago_ci_without_marker" in normalized_qa


def test_marker_without_date_is_warn_not_false_negative_conversion() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "pago_ci_marker_without_fecha_pago_ci" in normalized
    assert "'warning'" in normalized
    assert "excluir del risk scoring" in normalized
