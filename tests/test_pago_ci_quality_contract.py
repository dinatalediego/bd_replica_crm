from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_b_installs_effective_pago_ci_quality_override() -> None:
    install_py = (ROOT / "src" / "absorption_phase_b" / "install.py").read_text(encoding="utf-8")
    assert '"03b_sale_date_pago_ci.sql"' in install_py
    assert '"03c_pago_ci_quality_override.sql"' in install_py
    assert install_py.index('"03b_sale_date_pago_ci.sql"') < install_py.index('"03c_pago_ci_quality_override.sql"')


def test_hard_pago_ci_parse_gate_uses_latest_effective_value_per_proforma() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "distinct on (de.codigo)" in normalized
    assert "order by de.codigo, de.fecha_actualizacion desc nulls last, de.id desc" in normalized
    assert "pago_ci_date_parse_error" in normalized
    assert "latest_effective_value_per_proforma" in normalized


def test_historical_malformed_pago_ci_remains_visible_without_becoming_hard_gate() -> None:
    sql = (ROOT / "sql" / "20_absorption_phase_b" / "03c_pago_ci_quality_override.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert "pago_ci_historical_parse_debt" in normalized
    assert "'warning'" in normalized
    assert "all_raw_history" in normalized
