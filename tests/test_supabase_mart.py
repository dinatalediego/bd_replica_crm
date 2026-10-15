import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from replica_cygnus.supabase_mart import build_packet, transform, validate_packet


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_minimal_supabase_mart.py"
SECRET = b"synthetic-key-for-unit-tests-only-12345"


def sample(month="2026-01-01", stock=50, sales=3, code="DEMO"):
    return {"codigo_proyecto": code, "periodo_mes": month, "mes_vida": 1,
            "mes_calendario": date.fromisoformat(month).month, "fecha_corte": "2026-06-30",
            "mes_parcial": False, "stock_inicial": stock, "ventas_mes": sales,
            "stock_final": stock-sales, "dias_exposicion": stock*30,
            "unidades_revision": 0}


def test_allowlist_and_pseudonym():
    source = sample()
    packet = build_packet([source], SECRET)
    serialized = json.dumps(packet)
    assert "DEMO" not in serialized and "codigo_proyecto" not in serialized
    assert len(packet["rows"][0]["project_ref"]) == 64
    assert validate_packet(packet) == packet["rows"]
    assert transform(source, SECRET) == transform(source, SECRET)
    refreshed = sample()
    refreshed["fecha_corte"] = "2026-07-31"
    assert transform(source, SECRET)["source_hash"] == transform(refreshed, SECRET)["source_hash"]


def test_rejects_raw_and_stock_mismatch():
    source = sample()
    source["email"] = "private@example.com"
    try:
        transform(source, SECRET)
    except ValueError as exc:
        assert "source columns" in str(exc)
    else:
        raise AssertionError("raw field passed")
    source = sample()
    source["stock_final"] = 49
    try:
        transform(source, SECRET)
    except ValueError as exc:
        assert "Stock reconciliation" in str(exc)
    else:
        raise AssertionError("mismatch passed")


def test_packet_tamper_and_duplicate():
    packet = build_packet([sample()], SECRET)
    packet["rows"][0]["sales_units"] = 20
    try:
        validate_packet(packet)
    except ValueError as exc:
        assert "Tampered" in str(exc)
    else:
        raise AssertionError("tamper passed")
    try:
        build_packet([sample(), sample()], SECRET)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate passed")


def test_offline_prepare_and_publish_gate(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([sample(), sample("2026-02-01", 47, 2)]))
    packet = tmp_path / "packet.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "MEDALLIO_EXPORT_HMAC_KEY": SECRET.decode()}
    subprocess.run([sys.executable, str(SCRIPT), "prepare", "--fixture", str(fixture),
                    "--output", str(packet)], env=env, check=True, capture_output=True)
    assert len(validate_packet(json.loads(packet.read_text()))) == 2
    blocked = subprocess.run([sys.executable, str(SCRIPT), "publish", "--packet", str(packet)],
                             env=env, capture_output=True, text=True)
    assert blocked.returncode != 0 and "approval" in blocked.stderr


if __name__ == "__main__":
    test_allowlist_and_pseudonym()
    test_rejects_raw_and_stock_mismatch()
    test_packet_tamper_and_duplicate()
    with tempfile.TemporaryDirectory() as folder:
        test_offline_prepare_and_publish_gate(Path(folder))
    print("4 Supabase mart tests passed")
