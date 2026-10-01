from __future__ import annotations

import json
from pathlib import Path

from replica_cygnus.powerbi_adapter.service import (
    AdapterConfig,
    collect_entities,
    diff_snapshots,
    make_snapshot,
    scan,
    translation_plan,
)


def test_tmdl_measure_and_m_are_detected(tmp_path: Path) -> None:
    project = tmp_path / "Dashboard.SemanticModel" / "definition" / "tables"
    project.mkdir(parents=True)
    (project / "Procesos.tmdl").write_text(
        """table Procesos
    measure 'Iniciales' = COUNTROWS(Procesos)
    measure 'Iniciales visibles' = CALCULATE([Iniciales], ALLSELECTED(Procesos))
    partition Procesos = m
        mode: import
        source =
            let
                Source = PostgreSQL.Database("localhost", "medallio_dw")
            in
                Source
""",
        encoding="utf-8",
    )

    entities = collect_entities(tmp_path)
    kinds = {entity.kind for entity in entities}
    names = {entity.name for entity in entities}

    assert "dax_measure" in kinds
    assert "power_query_partition" in kinds
    assert "Procesos[Iniciales]" in names


def test_diff_classifies_m_and_filter_context_dax(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    new_root.mkdir()

    (old_root / "Ventas.m").write_text("let Source = 1 in Source", encoding="utf-8")
    (new_root / "Ventas.m").write_text("let Source = 2 in Source", encoding="utf-8")
    (new_root / "Medidas.dax").write_text(
        "Ventas visibles = CALCULATE([Ventas], ALLSELECTED(Ventas))",
        encoding="utf-8",
    )

    old_snapshot = make_snapshot(old_root, "old", collect_entities(old_root), [])
    new_snapshot = make_snapshot(new_root, "new", collect_entities(new_root), [])
    changes = diff_snapshots(old_snapshot, new_snapshot)
    plan = translation_plan(changes, new_snapshot)

    actions = {item.key: item.action for item in plan}
    assert any(action == "promote_to_backend" for action in actions.values())
    assert any(action == "keep_semantic_or_dual" for action in actions.values())


def test_scan_keeps_version_history_for_overwritten_pbip(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    state = tmp_path / "state"
    project = inbox / "Calidad"
    project.mkdir(parents=True)
    pbip = project / "Calidad.pbip"
    pbip.write_text('{"version":"1.0"}', encoding="utf-8")
    (project / "Ventas.m").write_text("let Source = 1 in Source", encoding="utf-8")

    cfg = AdapterConfig(
        source_dir=inbox,
        state_dir=state,
        pbi_tools_executable="definitely-not-installed-pbi-tools",
    )
    first = scan(cfg, pbip)

    (project / "Ventas.m").write_text("let Source = 2 in Source", encoding="utf-8")
    second = scan(cfg, pbip)

    assert first["snapshot_id"] != second["snapshot_id"]
    assert second["change_count"] >= 1
    manifest = json.loads((state / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["latest_snapshot"].startswith(second["snapshot_id"])
