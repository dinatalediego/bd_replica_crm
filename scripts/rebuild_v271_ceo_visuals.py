from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from medallio_evidence_outcome_v27 import (
    build_evidence_gates,
    summarize_gates,
    write_calibrated_ceo_visuals,
)


def main():
    summary_path = ROOT / "artifacts" / "medallio_ceo_briefing" / "evidence_outcome_summary.json"
    decisions_path = ROOT / "artifacts" / "medallio_ceo_briefing" / "decision_ledger_candidate.csv"

    if not summary_path.exists():
        raise SystemExit("Primero ejecuta Ambassador v2.7.1; falta evidence_outcome_summary.json")

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    gates = payload.get("gates") or []
    gate_summary = payload.get("gate_summary") or {}

    decisions = []
    if decisions_path.exists():
        import pandas as pd
        decisions = pd.read_csv(decisions_path).where(lambda x: x.notna(), None).to_dict("records")

    result = write_calibrated_ceo_visuals(ROOT, gates, gate_summary, decisions)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
