from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

TEXT_SUFFIXES = {".tmdl", ".dax", ".m", ".json", ".bim", ".pbir", ".pbip"}
INPUT_SUFFIXES = {".pbix", ".pbit", ".pbip"}
FILTER_FUNCS = ("CALCULATE", "ALLSELECTED", "SELECTEDVALUE", "ISINSCOPE", "TREATAS", "USERELATIONSHIP")
DOMAINS = {
    "sales_process_quality": ("inicial", "tubería", "contrato", "papel blanco", "flujo", "minuta", "separación", "administración"),
    "data_quality": ("dni", "celular", "teléfono", "email", "correo", "nombre", "apellido"),
    "ownership": ("propietario", "copropietario", "comprador"),
    "stock": ("stock", "disponible", "vendido", "por vender", "unidad"),
}


@dataclass(frozen=True)
class Entity:
    key: str
    kind: str
    name: str
    source_path: str
    content_hash: str
    expression: str
    domain: str | None


@dataclass(frozen=True)
class Change:
    change_type: str
    key: str
    kind: str
    name: str
    source_path: str
    old_hash: str | None
    new_hash: str | None


@dataclass(frozen=True)
class Recommendation:
    key: str
    action: str
    target_layer: str
    confidence: str
    reason: str
    domain: str | None


@dataclass(frozen=True)
class AdapterConfig:
    source_dir: Path
    state_dir: Path
    pbi_tools_executable: str = "pbi-tools"
    keep_extracted: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> "AdapterConfig":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            Path(raw.get("source_dir", r"C:\clientes\Cygnus\dashboards")),
            Path(raw.get("state_dir", ".state/powerbi_adapter")),
            str(raw.get("pbi_tools_executable", "pbi-tools")),
            bool(raw.get("keep_extracted", True)),
        )


def _hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sanitize(text: str) -> str:
    patterns = (
        r"(?i)(password|pwd)\s*=\s*([^;\r\n]+)",
        r"(?i)(access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|api[_ -]?key)\s*[:=]\s*([^,;\r\n}]+)",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: f"{m.group(1)}=<REDACTED>", text)
    return text


def _domain(text: str) -> str | None:
    folded = text.casefold()
    scores = {d: sum(k.casefold() in folded for k in keys) for d, keys in DOMAINS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def _entity(kind: str, name: str, rel: str, expression: str) -> Entity:
    expression = _sanitize(expression).strip()
    return Entity(f"{kind}::{name}", kind, name, rel, _hash(expression), expression, _domain(name + "\n" + expression))


def discover_latest(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de entrada: {source_dir}")
    candidates = [p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in INPUT_SUFFIXES]
    if not candidates:
        raise FileNotFoundError(f"No se encontró .pbix/.pbit/.pbip en {source_dir}")
    return max(candidates, key=lambda p: p.stat().st_mtime_ns)


def prepare_source(source: Path, state_dir: Path, executable: str) -> tuple[Path, str, list[str]]:
    if source.is_dir():
        return source, _hash(str(source.resolve())), []
    if source.suffix.lower() == ".pbip":
        return source.parent, _file_hash(source), []
    if source.suffix.lower() not in {".pbix", ".pbit"}:
        raise ValueError(f"Entrada Power BI no soportada: {source}")

    source_hash = _file_hash(source)
    out = state_dir / "extracted" / f"{source.stem}-{source_hash[:12]}"
    out.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(executable) or (executable if Path(executable).exists() else None)
    if exe is None:
        return out, source_hash, ["pbi-tools no está disponible; usa PBIP/TMDL o instala pbi-tools para extraer DAX/M."]

    run = subprocess.run([str(exe), "extract", str(source), "-extractFolder", str(out)], capture_output=True, text=True, check=False)
    if run.returncode:
        msg = _sanitize((run.stderr or run.stdout or "").strip())[-1000:]
        return out, source_hash, [f"pbi-tools extract falló (rc={run.returncode}): {msg}"]
    return out, source_hash, []


def _parse_tmdl(path: Path, rel: str, text: str) -> list[Entity]:
    table = path.stem
    m = re.search(r"(?mi)^\s*table\s+['\"]?([^'\"\r\n]+)['\"]?\s*$", text)
    if m:
        table = m.group(1).strip()
    entities = []
    pattern = re.compile(r"(?mi)^\s*(measure|calculatedColumn|calculatedTable|partition)\s+('([^']+)'|\"([^\"]+)\"|([^=\r\n]+?))\s*=\s*(.*)$")
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        raw_kind = match.group(1).lower()
        name = next(g for g in match.groups()[2:5] if g is not None).strip()
        block = text[match.start(): matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip()
        kind = {
            "measure": "dax_measure",
            "calculatedcolumn": "dax_calculated_column",
            "calculatedtable": "dax_calculated_table",
            "partition": "power_query_partition",
        }[raw_kind]
        qualified = f"{table}[{name}]" if raw_kind in {"measure", "calculatedcolumn"} else name
        entities.append(_entity(kind, qualified, rel, block))
    entities.append(_entity("tmdl_file", rel, rel, text))
    return entities


def _parse_dax(rel: str, text: str) -> list[Entity]:
    pattern = re.compile(r"(?m)^([^\s][^=\r\n]{0,180}?)\s*=\s*(.+)$")
    matches = []
    for m in pattern.finditer(text):
        name = m.group(1).strip().strip("[]")
        if name.upper().startswith("VAR ") or name.upper() == "RETURN":
            continue
        matches.append((m, name))
    if not matches:
        return [_entity("dax_file", rel, rel, text)]
    return [
        _entity("dax_measure", name, rel, text[m.start(): matches[i + 1][0].start() if i + 1 < len(matches) else len(text)])
        for i, (m, name) in enumerate(matches)
    ]


def _parse_json(rel: str, text: str) -> list[Entity]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [_entity("json_file", rel, rel, text)]
    entities = []
    model = payload.get("model") if isinstance(payload, dict) else None
    if isinstance(model, dict):
        for table in model.get("tables", []) or []:
            if not isinstance(table, dict):
                continue
            tname = str(table.get("name", "<table>"))
            for measure in table.get("measures", []) or []:
                if isinstance(measure, dict) and measure.get("name"):
                    expr = measure.get("expression", "")
                    expr = "\n".join(map(str, expr)) if isinstance(expr, list) else str(expr)
                    entities.append(_entity("dax_measure", f"{tname}[{measure['name']}]", rel, expr))
            for partition in table.get("partitions", []) or []:
                source = partition.get("source") if isinstance(partition, dict) else None
                if isinstance(source, dict) and source.get("expression") is not None:
                    expr = source["expression"]
                    expr = "\n".join(map(str, expr)) if isinstance(expr, list) else str(expr)
                    entities.append(_entity("power_query_m", f"{tname}::{partition.get('name', 'partition')}", rel, expr))
        for i, relationship in enumerate(model.get("relationships", []) or []):
            if isinstance(relationship, dict):
                entities.append(_entity("model_relationship", str(relationship.get("name") or f"relationship_{i+1}"), rel, json.dumps(relationship, sort_keys=True)))
    low = rel.casefold()
    if "visual" in low:
        entities.append(_entity("report_visual", rel, rel, json.dumps(payload, sort_keys=True)))
    elif "page" in low or "section" in low:
        entities.append(_entity("report_page", rel, rel, json.dumps(payload, sort_keys=True)))
    elif not entities:
        entities.append(_entity("json_file", rel, rel, json.dumps(payload, sort_keys=True)))
    return entities


def collect_entities(root: Path) -> list[Entity]:
    found: dict[str, Entity] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        rel, suffix = path.relative_to(root).as_posix(), path.suffix.lower()
        if suffix == ".tmdl":
            parsed = _parse_tmdl(path, rel, text)
        elif suffix == ".dax":
            parsed = _parse_dax(rel, text)
        elif suffix == ".m":
            parsed = [_entity("power_query_m", path.stem, rel, text)]
        else:
            parsed = _parse_json(rel, text)
        for item in parsed:
            key = item.key if item.key not in found else f"{item.kind}::{item.source_path}::{item.name}"
            found[key] = item if key == item.key else Entity(key, item.kind, item.name, item.source_path, item.content_hash, item.expression, item.domain)
    return sorted(found.values(), key=lambda x: x.key.casefold())


def make_snapshot(source: Path, source_hash: str, entities: list[Entity], warnings: list[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    fingerprint = "|".join(f"{x.key}:{x.content_hash}" for x in entities)
    sid = f"{now:%Y%m%dT%H%M%S%fZ}-{_hash(source.name + source_hash + fingerprint + now.isoformat())[:10]}"
    return {
        "schema_version": 1,
        "snapshot_id": sid,
        "captured_at": now.isoformat(timespec="microseconds"),
        "source": {"name": source.name, "path": str(source), "sha256": source_hash},
        "warnings": warnings,
        "entities": [asdict(x) for x in entities],
    }


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[Change]:
    before = {x["key"]: x for x in (previous or {}).get("entities", [])}
    after = {x["key"]: x for x in current.get("entities", [])}
    changes = []
    for key in sorted(after.keys() | before.keys()):
        old, new = before.get(key), after.get(key)
        if old is None:
            changes.append(Change("added", key, new["kind"], new["name"], new["source_path"], None, new["content_hash"]))
        elif new is None:
            changes.append(Change("removed", key, old["kind"], old["name"], old["source_path"], old["content_hash"], None))
        elif old["content_hash"] != new["content_hash"]:
            changes.append(Change("changed", key, new["kind"], new["name"], new["source_path"], old["content_hash"], new["content_hash"]))
    return changes


def recommend(change: Change, entity: dict[str, Any] | None) -> Recommendation:
    expr, domain = (entity or {}).get("expression", ""), (entity or {}).get("domain")
    if change.change_type == "removed":
        return Recommendation(change.key, "review_removal", "medallio_contract", "medium", "Validar si la regla también debe retirarse del backend.", domain)
    if change.kind in {"power_query_m", "power_query_partition"}:
        return Recommendation(change.key, "promote_to_backend", "sql_or_python", "high", "Power Query M es transformación de datos y es buen candidato para Medallio.", domain)
    if change.kind in {"dax_calculated_column", "dax_calculated_table"}:
        return Recommendation(change.key, "promote_to_backend", "sql_or_python", "medium", "La lógica fila-a-fila/tabular suele ser reutilizable en analytics.", domain)
    if change.kind == "dax_measure":
        if any(re.search(rf"\b{fn}\s*\(", expr.upper()) for fn in FILTER_FUNCS):
            return Recommendation(change.key, "keep_semantic_or_dual", "powerbi_semantic_layer", "high", "Depende de contexto de filtro DAX; no traducir mecánicamente.", domain)
        return Recommendation(change.key, "evaluate_backend_metric", "analytics_metric_contract", "medium", "Puede convertirse en métrica canónica si pasa pruebas de paridad.", domain)
    if change.kind.startswith("report_"):
        return Recommendation(change.key, "report_only", "powerbi_report", "high", "Cambio visual; no se promueve al backend.", domain)
    return Recommendation(change.key, "review_model_contract", "semantic_model_contract", "medium", "Revisar impacto en modelo, relaciones o mart.", domain)


def translation_plan(changes: list[Change], current: dict[str, Any]) -> list[Recommendation]:
    by_key = {x["key"]: x for x in current.get("entities", [])}
    return [recommend(c, by_key.get(c.key)) for c in changes]


def _load_previous(state_dir: Path) -> dict[str, Any] | None:
    manifest = state_dir / "manifest.json"
    if not manifest.exists():
        return None
    latest = json.loads(manifest.read_text(encoding="utf-8")).get("latest_snapshot")
    path = state_dir / "snapshots" / latest if latest else None
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None


def _save(state_dir: Path, snapshot: dict[str, Any], changes: list[Change], plan: list[Recommendation]) -> tuple[Path, Path]:
    snapshots, reports = state_dir / "snapshots", state_dir / "reports"
    snapshots.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    snap_path = snapshots / f"{snapshot['snapshot_id']}.json"
    plan_path = reports / f"{snapshot['snapshot_id']}_translation_plan.json"
    report_path = reports / f"{snapshot['snapshot_id']}_progress.md"
    snap_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps({"snapshot_id": snapshot["snapshot_id"], "changes": [asdict(x) for x in changes], "recommendations": [asdict(x) for x in plan], "warnings": snapshot["warnings"]}, indent=2, ensure_ascii=False), encoding="utf-8")
    by_key = {x.key: x for x in plan}
    lines = [
        f"# Power BI -> Medallio | {snapshot['snapshot_id']}",
        "",
        f"Fuente: {snapshot['source']['path']}",
        f"Entidades leídas: {len(snapshot['entities'])}",
        f"Cambios detectados: {len(changes)}",
        "",
        "| Cambio | Artefacto | Clase | Acción | Destino |",
        "|---|---|---|---|---|",
    ]
    for c in changes:
        rec = by_key[c.key]
        lines.append(f"| {c.change_type} | {c.name} | {c.kind} | {rec.action} | {rec.target_layer} |")
    if not changes:
        lines.append("| sin cambios | - | - | - | - |")
    if snapshot["warnings"]:
        lines += ["", "## Advertencias", ""] + [f"- {w}" for w in snapshot["warnings"]]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (state_dir / "manifest.json").write_text(json.dumps({"latest_snapshot": snap_path.name, "latest_plan": plan_path.name, "latest_report": report_path.name}, indent=2), encoding="utf-8")
    return plan_path, report_path


def scan(config: AdapterConfig, explicit_input: Path | None = None) -> dict[str, Any]:
    source = explicit_input or discover_latest(config.source_dir)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    previous = _load_previous(config.state_dir)
    prepared, source_hash, warnings = prepare_source(source, config.state_dir, config.pbi_tools_executable)
    entities = collect_entities(prepared)
    if not entities and source.suffix.lower() in {".pbix", ".pbit"}:
        warnings.append("No se recuperó lógica semántica; el diff será solo de versión del archivo.")
    snapshot = make_snapshot(source, source_hash, entities, warnings)
    changes = diff_snapshots(previous, snapshot)
    plan = translation_plan(changes, snapshot)
    plan_path, report_path = _save(config.state_dir, snapshot, changes, plan)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "source": str(source),
        "entity_count": len(entities),
        "change_count": len(changes),
        "changes_by_type": {k: sum(c.change_type == k for c in changes) for k in ("added", "changed", "removed")},
        "warnings": warnings,
        "plan_file": str(plan_path),
        "report_file": str(report_path),
    }
