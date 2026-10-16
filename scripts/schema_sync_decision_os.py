from __future__ import annotations

import argparse
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings
from schema_sync import SchemaComponent, _apply_component, _ensure_registry, _print_status


DECISION_OS = SchemaComponent(
    name="decision_os",
    files=(
        "sql/102_evidence_outcome_persistence/01_persistence_ledgers.sql",
        "sql/116_decision_os/01_contract.sql",
    ),
    expected_relations=(
        "decision_intelligence.decision_ledger",
        "decision_intelligence.action_log",
        "decision_intelligence.outcome_ledger",
        "decision_intelligence.economic_value_ledger",
        "decision_intelligence.decision_reviews",
        "decision_intelligence.decision_model_links",
        "decision_intelligence.v_economic_value_reconciliation",
        "decision_intelligence.v_decision_operating_system",
        "decision_intelligence.v_decision_queue",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Instala/verifica Medallio Decision OS sin tocar otros componentes del DW."
    )
    parser.add_argument("--status", action="store_true", help="Solo valida objetos y checksum.")
    parser.add_argument("--force", action="store_true", help="Reaplica el componente aunque no haya cambios.")
    args = parser.parse_args()

    settings = load_settings(require_source=False)
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        _ensure_registry(conn)
        if args.status:
            return _print_status(conn, root, (DECISION_OS,))
        result = _apply_component(conn, root, DECISION_OS, force=args.force)

    print(f"[DECISION_OS] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
