import json
import os
import subprocess
import sys
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from replica_cygnus.ai_review import (
    build_packet, call_responses, extract_output, request_body, review_record, validate_packet, validate_review,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "medallio_ai_review.py"


@contextmanager
def raises(error_type, match):
    try:
        yield
    except error_type as exc:
        assert re.search(match, str(exc)), str(exc)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def context():
    return {
        "meta": {"context_version": "2.9.0", "project_key": "SECRET-PROJECT", "project_name": "Private Towers"},
        "sources": {"commercial_history": {
            "status": "OK", "row_count": 2,
            "sample": [{"customer_email": "private@example.com", "customer_phone": "123456789"}],
            "profile": {"categorical_profile": {"customer_email": {"top": [["private@example.com", 1]]}}},
        }},
        "portfolio_comparison": {"stock_units": {"value": 34, "percentile": 75}},
        "predictive_context": {"issues": 2, "performance_rows": 0, "performance": [
            {"customer_email": "private@example.com"}]},
        "decision_context": {"actual_outcome_count": 0, "mature_outcome_count": 0,
                             "recent_decisions": [{"name": "Ana Private"}]},
        "layer_readiness": {"commercial": True, "outcome": False},
        "governance": {"highest_claim_level": "PREDICTIVE_INCUBATING",
                       "evidence_warning": "Private Towers"},
        "ai_hypotheses": [{"evidence": "private@example.com"}],
    }


def finding():
    return {"category": "OUTCOME_MEASUREMENT", "priority": "HIGH", "evidence_ids": ["F001"],
            "hypothesis": "¿Falta registrar resultados maduros?",
            "next_check": "Verificar el registro de resultados y su madurez."}


def response(review):
    return {"id": "resp_synthetic", "model": "test-model", "status": "completed", "usage": {
        "input_tokens": 100, "output_tokens": 50},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(review)}]}]}


def test_allowlist_excludes_raw_crm_and_is_stable():
    source = context()
    packet = build_packet(source)
    assert packet == build_packet(source)
    body = request_body(packet, "test-model")
    payload = json.dumps(body)
    for secret in ("SECRET-PROJECT", "Private Towers", "private@example.com", "123456789", "Ana Private"):
        assert secret not in payload
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert len(packet["facts"]) > 0


def test_rejects_unknown_contract_and_unsupported_reference():
    packet = build_packet(context())
    packet["facts"].append({"id": f"F{len(packet['facts'])+1:03}", "path": "sources.raw.sample", "value": "private@example.com"})
    with raises(ValueError, match="Unapproved fact"):
        validate_packet(packet)
    packet = build_packet(context())
    result = {"findings": [finding()], "abstain_reason": ""}
    result["findings"][0]["evidence_ids"] = ["F999"]
    with raises(ValueError, match="reference"):
        validate_review(packet, result)
    result["findings"][0]["evidence_ids"] = ["F001"]
    result["findings"][0]["hypothesis"] = "ROI del 50% confirmado"
    with raises(ValueError, match="figure"):
        validate_review(packet, result)


def test_completed_response_and_refusal():
    packet = build_packet(context())
    result = {"findings": [finding()], "abstain_reason": ""}
    raw = response(result)
    assert review_record(packet, extract_output(raw), raw)["status"] == "DRAFT_REVIEW_REQUIRED"
    with raises(ValueError, match="incomplete"):
        extract_output({"status": "incomplete", "output": []})
    assert validate_review(packet, {"findings": [], "abstain_reason": "No hay evidencia suficiente"})


def test_no_api_call_without_key_and_explicit_gate(tmp_path):
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(build_packet(context())))
    output = tmp_path / "review.json"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    cmd = [sys.executable, str(SCRIPT), "review", "--packet", str(packet_path),
           "--output", str(output), "--send"]
    run = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert run.returncode != 0 and "approval" in run.stderr
    assert not output.exists()
    with raises(ValueError, match="OPENAI_API_KEY"):
        call_responses(request_body(build_packet(context()), "test-model"), "")


def test_offline_fixture_and_feedback(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(context()))
    packet_path, fixture, record, feedback = [tmp_path / name for name in (
        "packet.json", "response.json", "review.json", "feedback.jsonl")]
    fixture.write_text(json.dumps(response({"findings": [finding()], "abstain_reason": ""})))
    commands = [
        ["prepare", "--context", str(context_path), "--output", str(packet_path)],
        ["review", "--packet", str(packet_path), "--fixture-response", str(fixture), "--output", str(record)],
        ["feedback", "--record", str(record), "--finding-index", "0", "--verdict", "REJECT",
         "--reviewer", "analyst", "--note", "Falta evidencia externa", "--output", str(feedback)],
    ]
    for command in commands:
        subprocess.run([sys.executable, str(SCRIPT), *command], env=env, check=True, capture_output=True)
    assert json.loads(record.read_text())["status"] == "DRAFT_REVIEW_REQUIRED"
    assert json.loads(feedback.read_text())["verdict"] == "REJECT"
    again = subprocess.run([sys.executable, str(SCRIPT), *commands[1]], env=env, capture_output=True)
    assert again.returncode != 0


if __name__ == "__main__":
    test_allowlist_excludes_raw_crm_and_is_stable()
    test_rejects_unknown_contract_and_unsupported_reference()
    test_completed_response_and_refusal()
    with tempfile.TemporaryDirectory() as folder:
        test_no_api_call_without_key_and_explicit_gate(Path(folder))
    with tempfile.TemporaryDirectory() as folder:
        test_offline_fixture_and_feedback(Path(folder))
    print("5 AI review tests passed")
