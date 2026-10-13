"""Export a complete, private Medallio conversation diagnostic for review."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from replica_cygnus.conversations.extraction import RULESET_VERSION

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = "Chat de WhatsApp con Cygnus - Ventas.txt"
EXPORTS = {
    "control/sources.jsonl": "SELECT * FROM etl_control.conversation_sources WHERE source_id=%s",
    "control/import_runs.jsonl": "SELECT * FROM etl_control.conversation_import_runs WHERE source_id=%s ORDER BY run_id",
    "raw/messages.jsonl": "SELECT * FROM raw_conversations.messages WHERE source_id=%s ORDER BY ordinal",
    "analytics/events_all_versions.jsonl": "SELECT * FROM analytics.conversation_events WHERE source_id=%s ORDER BY first_run_id,event_id",
    "analytics/events_current.jsonl": "SELECT * FROM analytics.v_conversation_events_current WHERE source_id=%s ORDER BY message_at,event_id",
    "analytics/visit_reports.jsonl": "SELECT * FROM analytics.v_conversation_visit_reports WHERE source_id=%s ORDER BY message_at,event_id",
    "analytics/visits_daily.jsonl": "SELECT * FROM analytics.v_conversation_visits_daily WHERE source_id=%s ORDER BY reported_date,project_name,venue_type",
    "analytics/project_hourly.jsonl": "SELECT * FROM analytics.v_conversation_project_hourly WHERE source_id=%s ORDER BY message_hour,project_name",
    "analytics/project_day_signals.jsonl": "SELECT * FROM analytics.v_conversation_project_day_signals WHERE source_id=%s ORDER BY reported_date,project_name",
    "analytics/daily_rhythm.jsonl": "SELECT * FROM analytics.v_conversation_daily_rhythm WHERE source_id=%s ORDER BY message_date,hour_of_day",
    "analytics/sale_reactions.jsonl": "SELECT * FROM analytics.v_conversation_sale_reactions WHERE source_id=%s ORDER BY announcement_at,event_id",
}


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


def _revision() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _export_query(conn, archive: zipfile.ZipFile, name: str, sql: str,
                  source_id: int) -> dict:
    digest = hashlib.sha256()
    count = 0
    columns: list[str] = []
    with conn.cursor() as cur:
        cur.execute(sql, (source_id,))
        columns = [column.name for column in cur.description]
        with archive.open(name, "w") as member:
            while rows := cur.fetchmany(500):
                for row in rows:
                    payload = json.dumps(dict(zip(columns, row)), ensure_ascii=False,
                                         default=_json_value, separators=(",", ":")) + "\n"
                    encoded = payload.encode("utf-8")
                    member.write(encoded)
                    digest.update(encoded)
                    count += 1
    return {"rows": count, "columns": columns, "sha256": digest.hexdigest()}


def build_archive(conn, output: Path, source_name: str) -> dict:
    """Export a consistent database snapshot; the temporary ZIP is removed on error."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Ya existe {output}; elige otro --output")
    temporary = output.with_name(output.name + ".partial")
    if temporary.exists():
        raise FileExistsError(f"Ya existe un archivo parcial: {temporary}")

    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("SELECT source_id, message_count, current_ruleset_version "
                        "FROM etl_control.conversation_sources WHERE source_name=%s", (source_name,))
            source = cur.fetchone()
            if source is None:
                raise ValueError(f"No existe la fuente {source_name!r} en Medallio; "
                                 "ejecuta primero la importación con ese nombre.")
            source_id, message_count, database_ruleset = source

        manifest = {
            "format": "medallio-conversations-diagnostic-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_name": source_name,
            "source_id": source_id,
            "message_count_control": message_count,
            "database_ruleset_version": database_ruleset,
            "code_ruleset_version": RULESET_VERSION,
            "code_commit": _revision(),
            "files": {},
        }
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            for name, sql in EXPORTS.items():
                manifest["files"][name] = _export_query(conn, archive, name, sql, source_id)
            contract = ROOT / "sql" / "102_conversaciones" / "01_contract.sql"
            archive.write(contract, "contract/01_contract.sql")
            archive.writestr("README.txt", (
                "Diagnóstico privado de conversaciones de Medallio.\n"
                "Contiene texto original, remitentes y posibles datos personales.\n"
                "No subir a Git ni compartir fuera del chat de análisis autorizado.\n"
                "Los archivos JSONL contienen un objeto JSON por línea; una línea puede contener\n"
                "saltos de línea escapados dentro de body y raw_message.\n"
                "manifest.json contiene recuentos, columnas y SHA-256 de cada JSONL.\n"
                "events_all_versions conserva reglas históricas; events_current es la versión activa.\n"
                "El conteo de visitas es declarado en WhatsApp y puede contener solapamientos.\n"
            ))
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                         indent=2, default=_json_value) + "\n")
        with zipfile.ZipFile(temporary) as archive:
            if bad_file := archive.testzip():
                raise IOError(f"Archivo ZIP dañado: {bad_file}")
        temporary.replace(output)
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    from replica_cygnus.connections import connect_postgres
    from replica_cygnus.settings import load_settings

    parser = argparse.ArgumentParser(description="Crea ZIP privado con evidencia y vistas de conversaciones.")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE,
                        help="Nombre exacto del TXT cargado como fuente.")
    parser.add_argument("--output", type=Path,
                        help="Ruta de salida; por defecto conversaciones/diagnostico_<fecha>.zip")
    args = parser.parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or ROOT / "conversaciones" / f"diagnostico_conversaciones_{timestamp}.zip"
    with connect_postgres(load_settings(require_source=False)) as conn:
        manifest = build_archive(conn, output, args.source_name)
    print(f"[CONVERSACIONES][ZIP] {output.resolve()}")
    print(f"[CONVERSACIONES][FUENTE] {manifest['source_name']} / reglas "
          f"DB={manifest['database_ruleset_version']} código={manifest['code_ruleset_version']}")
    for name, info in manifest["files"].items():
        print(f"  {name}: {info['rows']} filas")
    if manifest["database_ruleset_version"] != manifest["code_ruleset_version"]:
        print("[AVISO] Ejecuta run_conversaciones_manual.bat antes de exportar: "
              "la base aún usa otra versión de reglas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
