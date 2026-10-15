from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import logging
import mimetypes
import os
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from decimal import Decimal
from zoneinfo import ZoneInfo

import nbformat
import pandas as pd
from nbconvert.preprocessors import ExecutePreprocessor
from jupyter_client.kernelspec import KernelSpecManager
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from medallio_evidence_outcome_v27 import enrich_digest_v27
from medallio_predictive_gate_v28 import refresh_predictive_gate_v28


BASE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar.events",
]
CHAT_SCOPE = "https://www.googleapis.com/auth/chat.messages.create"


def required_google_scopes(cfg: dict) -> list[str]:
    scopes = list(BASE_SCOPES)
    chat = cfg.get("google", {}).get("chat", {})
    if chat.get("enabled") and chat.get("space_name"):
        scopes.append(CHAT_SCOPE)
    return scopes

EXTENSIONS = {".png", ".csv", ".json", ".pdf", ".xlsx"}

ARTIFACT_WEIGHTS = {
    "board_summary": 160,
    "ceo_decision_queue": 155,
    "ceo_control_tower_summary": 150,
    "ceo_confidence": 145,
    "value_at_stake": 140,
    "forecast_confidence": 135,
    "ceo_action_board": 130,
    "ai_portfolio": 125,
    "ceo_heatmap": 120,
    "decision": 110,
    "forecast": 105,
    "value": 100,
    "confidence": 95,
    "ceo": 90,
    "summary": 85,
    "governance": 75,
    "drift": 70,
}


def find_repo_root() -> Path:
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / ".env.example").exists():
            return candidate
    return p


def load_config(root: Path) -> dict:
    path = root / "config" / "medallio_ambassador_v2.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Falta {path}. Copia medallio_ambassador_v2.example.json."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_runtime(root: Path, cfg: dict):
    for key in ["state_dir", "runtime_dir"]:
        (root / cfg["paths"][key]).mkdir(parents=True, exist_ok=True)


def setup_logging(root: Path, cfg: dict):
    d = root / cfg["paths"]["runtime_dir"] / "logs"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{datetime.now():%Y-%m-%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(p, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def stable_hash(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, path)


class FileLock:
    def __init__(self, path: Path, stale_seconds=4 * 3600):
        self.path = path
        self.stale_seconds = stale_seconds
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age > self.stale_seconds:
                self.path.unlink(missing_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode())
            return self
        except FileExistsError:
            raise RuntimeError(f"Ambassador ya está activo: {self.path}")

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.path.unlink(missing_ok=True)


# ---------------------------------------------------------------------
# AUTH / GOOGLE SERVICES
# ---------------------------------------------------------------------

def google_credentials(root: Path, cfg: dict) -> Credentials:
    token = root / cfg["paths"]["token_file"]
    if not token.exists():
        raise FileNotFoundError(
            f"Falta {token}. Ejecuta scripts\\google_workspace_oauth_v2.py"
        )

    scopes = required_google_scopes(cfg)
    creds = Credentials.from_authorized_user_file(str(token), scopes)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")

    if not creds.valid or not creds.has_scopes(scopes):
        missing = sorted(set(scopes) - set(creds.scopes or []))
        raise RuntimeError(
            "El token OAuth no tiene los scopes requeridos por la configuración actual. "
            f"Faltan: {missing}. Reautoriza con google_workspace_oauth_v2.py."
        )
    return creds


def google_services(creds: Credentials) -> dict:
    return {
        "gmail": build("gmail", "v1", credentials=creds, cache_discovery=False),
        "drive": build("drive", "v3", credentials=creds, cache_discovery=False),
        "sheets": build("sheets", "v4", credentials=creds, cache_discovery=False),
        "slides": build("slides", "v1", credentials=creds, cache_discovery=False),
        "docs": build("docs", "v1", credentials=creds, cache_discovery=False),
        "calendar": build("calendar", "v3", credentials=creds, cache_discovery=False),
        "chat": build("chat", "v1", credentials=creds, cache_discovery=False),
    }


# ---------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------

def state_dir(root: Path, cfg: dict) -> Path:
    p = root / cfg["paths"]["state_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def last_summary(root: Path, cfg: dict) -> dict:
    return read_json(state_dir(root, cfg) / "last_summary.json", {})


def save_last_summary(root: Path, cfg: dict, summary: dict):
    write_json_atomic(state_dir(root, cfg) / "last_summary.json", summary)


def google_assets(root: Path, cfg: dict) -> dict:
    return read_json(state_dir(root, cfg) / "google_assets.json", {})


def save_google_assets(root: Path, cfg: dict, assets: dict):
    write_json_atomic(state_dir(root, cfg) / "google_assets.json", assets)


def fingerprints(root: Path, cfg: dict) -> dict:
    return read_json(
        state_dir(root, cfg) / "fingerprints.json",
        {"calendar": [], "chat": []},
    )


def seen(root: Path, cfg: dict, channel: str, payload) -> bool:
    fp = stable_hash(payload)
    return fp in fingerprints(root, cfg).get(channel, [])


def mark_seen(root: Path, cfg: dict, channel: str, payload, keep=200):
    data = fingerprints(root, cfg)
    values = data.setdefault(channel, [])
    fp = stable_hash(payload)
    if fp not in values:
        values.append(fp)
    data[channel] = values[-keep:]
    write_json_atomic(state_dir(root, cfg) / "fingerprints.json", data)


# ---------------------------------------------------------------------
# NOTEBOOK EXECUTION
# ---------------------------------------------------------------------

def resolve_kernel(nb, preferred: str) -> str:
    available = KernelSpecManager().find_kernel_specs()
    metadata = nb.metadata.get("kernelspec", {}).get("name")
    for k in [preferred, "medallio_dw", metadata, "python3"]:
        if k and k in available:
            return k
    raise RuntimeError(f"No hay kernel usable. Disponibles={sorted(available)}")


def execute_notebook(root: Path, rel: str, timeout: int, preferred: str) -> dict:
    p = root / rel
    started = datetime.now()
    result = {
        "notebook": rel,
        "status": "MISSING",
        "seconds": 0,
        "error": "",
        "kernel": "",
    }

    if not p.exists():
        result["error"] = f"No existe {p}"
        return result

    try:
        nb = nbformat.read(p, as_version=4)
        kernel = resolve_kernel(nb, preferred)
        result["kernel"] = kernel
        logging.info(
            "Notebook %s | kernel=%s | timeout=%ss",
            rel,
            kernel,
            timeout,
        )
        ep = ExecutePreprocessor(
            timeout=timeout,
            startup_timeout=120,
            kernel_name=kernel,
            allow_errors=False,
        )
        ep.preprocess(nb, {"metadata": {"path": str(root)}})
        result["status"] = "OK"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {exc}"
        logging.exception("Notebook falló: %s", rel)

    result["seconds"] = round((datetime.now() - started).total_seconds(), 1)
    return result


# ---------------------------------------------------------------------
# ARTIFACT POLICY
# ---------------------------------------------------------------------

def artifact_score(path: Path) -> int:
    n = path.name.lower()
    score = max([v for k, v in ARTIFACT_WEIGHTS.items() if k in n] or [0])
    score += {
        ".png": 25,
        ".csv": 16,
        ".json": 14,
        ".pdf": 8,
        ".xlsx": 6,
    }.get(path.suffix.lower(), 0)
    return score


def current_run_artifacts(root: Path, cfg: dict, since_epoch: float) -> list[Path]:
    files = []
    for rel in cfg["artifact_roots"]:
        d = root / rel
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in EXTENSIONS:
                continue
            if p.stat().st_mtime < since_epoch - 5:
                continue
            files.append(p)

    return sorted(
        files,
        key=lambda p: (artifact_score(p), p.stat().st_mtime),
        reverse=True,
    )


def choose_artifacts(
    files: list[Path],
    max_n: int,
    budget_mb: float,
) -> list[Path]:
    budget = int(budget_mb * 1024 * 1024)
    out, used = [], 0
    for p in files:
        size = p.stat().st_size
        if len(out) >= max_n:
            break
        if used + size > budget:
            continue
        out.append(p)
        used += size
    return out


# ---------------------------------------------------------------------
# EXECUTIVE DIGEST
# ---------------------------------------------------------------------

def read_csv_records(path: Path, n=5):
    try:
        return pd.read_csv(path).head(n).to_dict("records")
    except Exception:
        return []


def build_digest(
    root: Path,
    results: list[dict],
    previous: dict,
    cfg: dict,
) -> dict:
    ceo = root / "artifacts" / "medallio_ceo_briefing"
    summary = read_json(ceo / "board_summary.json", {})
    decisions = read_csv_records(ceo / "ceo_decision_queue.csv", 5)

    defaults = [
        "platform_coverage_pct",
        "forecast_wape_pct",
        "forecast_bias",
        "open_actions",
        "risk_alerts",
        "outcomes",
        "trust_score_pct",
    ]
    for k in defaults:
        summary.setdefault(k, None)

    mat = cfg["communication_policy"]["materiality"]
    changes = []

    def delta(key, threshold, label, suffix=""):
        cur, prev = summary.get(key), previous.get(key)
        if cur is None or prev is None:
            return
        try:
            d = float(cur) - float(prev)
        except Exception:
            return
        if abs(d) >= threshold:
            changes.append(f"{label}: {d:+.1f}{suffix}")

    delta("forecast_wape_pct", mat["wape_change_pp"], "WAPE", " pp")
    delta("platform_coverage_pct", mat["coverage_change_pp"], "Cobertura", " pp")
    delta("trust_score_pct", mat["trust_score_change_pp"], "Trust", " pp")
    delta("open_actions", mat["open_actions_delta"], "Acciones abiertas")
    delta("risk_alerts", mat["risk_alerts_delta"], "Alertas")

    errors = [r for r in results if r["status"] == "ERROR"]
    if errors:
        changes.insert(0, f"{len(errors)} notebook(s) con error")

    risk = int(summary.get("risk_alerts") or 0)
    wape = summary.get("forecast_wape_pct")
    coverage = summary.get("platform_coverage_pct")

    severity = "normal"
    if (
        errors
        or risk >= 2
        or (wape is not None and float(wape) >= 35)
        or (coverage is not None and float(coverage) < 75)
    ):
        severity = "critical"
    elif (
        risk >= 1
        or (wape is not None and float(wape) >= 25)
        or (coverage is not None and float(coverage) < 90)
    ):
        severity = "high"
    elif changes:
        severity = "medium"

    headline = summary.get("headline") or (
        "Medallio estable, sin cambios materiales."
        if not changes
        else "Medallio presenta cambios que merecen atención."
    )

    return {
        "summary": summary,
        "decisions": decisions,
        "changes": changes[:5],
        "severity": severity,
        "headline": headline,
        "notebooks": results,
    }


# ---------------------------------------------------------------------
# DRIVE
# ---------------------------------------------------------------------

def ensure_folder(drive, name: str, parent: str | None = None) -> dict:
    escaped = name.replace("'", "\\'")
    parts = [
        f"name='{escaped}'",
        "mimeType='application/vnd.google-apps.folder'",
        "trashed=false",
    ]
    if parent:
        parts.append(f"'{parent}' in parents")

    res = drive.files().list(
        q=" and ".join(parts),
        spaces="drive",
        fields="files(id,name,webViewLink)",
        pageSize=10,
    ).execute()

    if res.get("files"):
        return res["files"][0]

    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent:
        body["parents"] = [parent]

    return drive.files().create(
        body=body,
        fields="id,name,webViewLink",
    ).execute()


def upload_drive_vault(
    root: Path,
    cfg: dict,
    services: dict,
    files: list[Path],
    slot: str,
) -> dict:
    if not cfg["google"]["drive"]["enabled"]:
        return {"folder_url": None, "uploaded": []}

    drive = services["drive"]
    assets = google_assets(root, cfg)

    vault_id = assets.get("drive_root_id")
    if not vault_id:
        folder = ensure_folder(
            drive,
            cfg["google"]["drive"]["root_folder_name"],
        )
        vault_id = folder["id"]
        assets["drive_root_id"] = vault_id
        save_google_assets(root, cfg, assets)

    day = ensure_folder(drive, datetime.now().strftime("%Y-%m-%d"), vault_id)
    slot_folder = ensure_folder(drive, slot.title(), day["id"])

    uploaded = []
    for p in files:
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        media = MediaFileUpload(str(p), mimetype=mime, resumable=False)
        item = drive.files().create(
            body={"name": p.name, "parents": [slot_folder["id"]]},
            media_body=media,
            fields="id,name,webViewLink,size",
        ).execute()
        uploaded.append(item)

    return {
        "folder_url": slot_folder.get("webViewLink"),
        "folder_id": slot_folder["id"],
        "uploaded": uploaded,
    }


# ---------------------------------------------------------------------
# SHEETS MEMORY
# ---------------------------------------------------------------------

def ensure_sheet_register(root: Path, cfg: dict, sheets) -> tuple[str, str]:
    assets = google_assets(root, cfg)
    sid = assets.get("sheets_id")
    if sid:
        return sid, assets.get("sheets_url")

    body = {
        "properties": {"title": cfg["google"]["sheets"]["spreadsheet_name"]},
        "sheets": [
            {"properties": {"title": x}}
            for x in ["RUNS", "DECISIONS", "ARTIFACTS", "OUTCOMES"]
        ],
    }
    res = sheets.spreadsheets().create(
        body=body,
        fields="spreadsheetId,spreadsheetUrl",
    ).execute()

    assets["sheets_id"] = res["spreadsheetId"]
    assets["sheets_url"] = res["spreadsheetUrl"]
    save_google_assets(root, cfg, assets)
    return res["spreadsheetId"], res["spreadsheetUrl"]



def google_json_scalar(value):
    """
    Google API discovery serializes request bodies with stdlib json.dumps.
    Normalize PostgreSQL Decimal/date/numpy values before sending.
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        # preserve integers when exact, otherwise send float
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    # numpy/pandas scalar
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return google_json_scalar(value.item())
        except Exception:
            pass

    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(
            value,
            ensure_ascii=False,
            default=lambda x: (
                float(x) if isinstance(x, Decimal)
                else x.isoformat() if isinstance(x, (datetime, date))
                else str(x)
            ),
        )

    # NaN / NaT
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def google_json_rows(rows):
    return [
        [google_json_scalar(value) for value in row]
        for row in rows
    ]


def sheet_append(sheets, sid: str, tab: str, rows: list[list]):
    if not rows:
        return
    sheets.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"{tab}!A:Z",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": google_json_rows(rows)},
    ).execute()



def ensure_sheet_tabs(sheets, sid: str, tabs: dict[str, list[str]]):
    meta = sheets.spreadsheets().get(
        spreadsheetId=sid,
        fields="sheets.properties(title)",
    ).execute()
    existing = {x["properties"]["title"] for x in meta.get("sheets", [])}
    requests = [
        {"addSheet": {"properties": {"title": name}}}
        for name in tabs
        if name not in existing
    ]
    if requests:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sid,
            body={"requests": requests},
        ).execute()

    existing_after = existing | set(tabs.keys())
    for name, headers in tabs.items():
        # We only seed headers if the sheet was just created or empty.
        values = sheets.spreadsheets().values().get(
            spreadsheetId=sid,
            range=f"{name}!A1:A1",
        ).execute().get("values", [])
        if not values:
            sheets.spreadsheets().values().update(
                spreadsheetId=sid,
                range=f"{name}!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()


def update_sheets_memory(
    root: Path,
    cfg: dict,
    services: dict,
    digest: dict,
    uploaded: list[dict],
    slot: str,
) -> str | None:
    if not cfg["google"]["sheets"]["enabled"]:
        return None

    sheets = services["sheets"]
    sid, url = ensure_sheet_register(root, cfg, sheets)

    ensure_sheet_tabs(
        sheets,
        sid,
        {
            "EVIDENCE_GATES": [
                "timestamp", "slot", "claim_level", "gate_name", "status",
                "score", "threshold", "reason", "missing_evidence"
            ],
            "DECISION_OUTCOME": [
                "timestamp", "slot", "decision_id", "project_key", "decision_title",
                "owner", "quantification_status", "value_at_risk",
                "value_to_capture", "action_cost", "confidence", "expected_roi",
                "outcome_status", "missing_evidence", "next_required_step"
            ],
        },
    )

    now = datetime.now().isoformat(timespec="seconds")
    s = digest["summary"]

    sheet_append(
        sheets,
        sid,
        "RUNS",
        [[
            now,
            slot,
            digest["severity"],
            digest["headline"],
            s.get("platform_coverage_pct"),
            s.get("forecast_wape_pct"),
            s.get("forecast_bias"),
            s.get("open_actions"),
            s.get("risk_alerts"),
            s.get("outcomes"),
            s.get("trust_score_pct"),
            sum(r["status"] == "OK" for r in digest["notebooks"]),
            sum(r["status"] == "ERROR" for r in digest["notebooks"]),
        ]],
    )

    for d in digest["decisions"]:
        sheet_append(
            sheets,
            sid,
            "DECISIONS",
            [[
                now,
                slot,
                d.get("decision", d.get("signal", "")),
                d.get("why", d.get("evidence", "")),
                d.get("owner", ""),
                d.get("urgency", ""),
                d.get("confidence", ""),
                digest["severity"],
            ]],
        )

    for a in uploaded:
        sheet_append(
            sheets,
            sid,
            "ARTIFACTS",
            [[
                now,
                slot,
                a.get("name"),
                a.get("webViewLink"),
                a.get("size"),
            ]],
        )

    v27 = digest.get("v27") or {}
    for g in v27.get("gates", []):
        sheet_append(
            sheets,
            sid,
            "EVIDENCE_GATES",
            [[
                now, slot, g.get("claim_level"), g.get("gate_name"),
                g.get("gate_status"), g.get("score"), g.get("threshold"),
                g.get("reason"), g.get("missing_evidence")
            ]],
        )

    for row in v27.get("decision_outcome_gap", []):
        sheet_append(
            sheets,
            sid,
            "DECISION_OUTCOME",
            [[
                now, slot, row.get("decision_id"), row.get("project_key"),
                row.get("decision_title"), row.get("owner"),
                row.get("quantification_status"), row.get("value_at_risk"),
                row.get("value_to_capture"), row.get("action_cost"),
                row.get("confidence"), row.get("expected_roi"),
                row.get("outcome_status"), row.get("missing_evidence"),
                row.get("next_required_step")
            ]],
        )

    return url or f"https://docs.google.com/spreadsheets/d/{sid}"




# ---------------------------------------------------------------------
# SLIDES — v2.5 CLIENT NARRATIVE LAYER
# ---------------------------------------------------------------------

BRAND = {
    "navy": {"red": 22/255, "green": 48/255, "blue": 88/255},
    "blue": {"red": 43/255, "green": 108/255, "blue": 176/255},
    "sky": {"red": 227/255, "green": 239/255, "blue": 250/255},
    "green": {"red": 35/255, "green": 102/255, "blue": 79/255},
    "amber": {"red": 180/255, "green": 120/255, "blue": 0/255},
    "red": {"red": 156/255, "green": 42/255, "blue": 42/255},
    "gray": {"red": 92/255, "green": 92/255, "blue": 92/255},
    "light": {"red": 246/255, "green": 248/255, "blue": 251/255},
    "white": {"red": 1, "green": 1, "blue": 1},
}


def fmt_metric(value, pct=False, decimals=1, default="N/A"):
    if value is None or value == "":
        return default
    try:
        n = float(value)
        if pct:
            return f"{n:.{decimals}f}%"
        if n.is_integer():
            return str(int(n))
        return f"{n:.{decimals}f}"
    except Exception:
        return str(value)


def safe_text(value, default="-"):
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _norm_name(value):
    return str(value).strip().lower().replace(" ", "_")


def slide_shape(slide_id, object_id, x, y, w, h, shape_type="TEXT_BOX"):
    return {
        "createShape": {
            "objectId": object_id,
            "shapeType": shape_type,
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": w, "unit": "PT"},
                    "height": {"magnitude": h, "unit": "PT"},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": x,
                    "translateY": y,
                    "unit": "PT",
                },
            },
        }
    }


def slide_textbox(
    slide_id,
    object_id,
    text,
    x,
    y,
    w,
    h,
    font_size=18,
    bold=False,
    color=None,
    bg=None,
    align="START",
):
    req = [
        slide_shape(slide_id, object_id, x, y, w, h, "TEXT_BOX"),
        {"insertText": {"objectId": object_id, "text": text}},
        {
            "updateTextStyle": {
                "objectId": object_id,
                "style": {
                    "fontFamily": "Arial",
                    "fontSize": {"magnitude": font_size, "unit": "PT"},
                    "bold": bold,
                    **(
                        {"foregroundColor": {"opaqueColor": {"rgbColor": color}}}
                        if color else {}
                    ),
                },
                "textRange": {"type": "ALL"},
                "fields": "fontFamily,fontSize,bold,foregroundColor",
            }
        },
        {
            "updateParagraphStyle": {
                "objectId": object_id,
                "style": {"alignment": align},
                "textRange": {"type": "ALL"},
                "fields": "alignment",
            }
        },
    ]
    if bg:
        req.append(
            {
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {
                            "solidFill": {"color": {"rgbColor": bg}, "alpha": 1}
                        }
                    },
                    "fields": "shapeBackgroundFill.solidFill.color,shapeBackgroundFill.solidFill.alpha",
                }
            }
        )
    return req


def slide_rect(slide_id, object_id, x, y, w, h, fill, border=None):
    req = [slide_shape(slide_id, object_id, x, y, w, h, "RECTANGLE")]
    props = {
        "shapeBackgroundFill": {
            "solidFill": {"color": {"rgbColor": fill}, "alpha": 1}
        }
    }
    fields = "shapeBackgroundFill.solidFill.color,shapeBackgroundFill.solidFill.alpha"
    if border:
        props["outline"] = {
            "outlineFill": {"solidFill": {"color": {"rgbColor": border}, "alpha": 1}},
            "weight": {"magnitude": 1, "unit": "PT"},
        }
        fields += ",outline.outlineFill.solidFill.color,outline.outlineFill.solidFill.alpha,outline.weight"
    req.append(
        {
            "updateShapeProperties": {
                "objectId": object_id,
                "shapeProperties": props,
                "fields": fields,
            }
        }
    )
    return req


def severity_color(severity: str):
    return {
        "normal": BRAND["green"],
        "medium": BRAND["amber"],
        "high": BRAND["red"],
        "critical": BRAND["red"],
    }.get(severity, BRAND["blue"])


def kpi_card_requests(slide_id, idx, label, value, x, y, color):
    card = f"card_{idx}"
    label_id = f"label_{idx}"
    value_id = f"value_{idx}"
    req = []
    req += slide_rect(slide_id, card, x, y, 125, 76, BRAND["light"], BRAND["sky"])
    req += slide_textbox(
        slide_id, label_id, label, x + 9, y + 7, 105, 18,
        font_size=10, bold=True, color=BRAND["gray"]
    )
    req += slide_textbox(
        slide_id, value_id, value, x + 9, y + 30, 106, 28,
        font_size=19, bold=True, color=color
    )
    return req


def bullet_block(title, items):
    if not items:
        items = ["-"]
    return title + "\n" + "\n".join(f"• {safe_text(x)}" for x in items)


def evidence_grade(digest: dict) -> tuple[str, str]:
    s = digest["summary"]
    coverage = s.get("platform_coverage_pct")
    trust = s.get("trust_score_pct")
    outcomes = s.get("outcomes")

    scores = []
    try:
        if coverage is not None:
            scores.append(min(max(float(coverage), 0), 100))
    except Exception:
        pass
    try:
        if trust is not None:
            scores.append(min(max(float(trust), 0), 100))
    except Exception:
        pass
    try:
        if outcomes is not None:
            scores.append(min(float(outcomes) * 5, 100))
    except Exception:
        pass

    if not scores:
        return "C", "Evidencia todavía insuficiente para recomendaciones fuertes."

    score = sum(scores) / len(scores)
    if score >= 80:
        return "A", "Evidencia suficiente para recomendación ejecutiva."
    if score >= 60:
        return "B", "Evidencia razonable; validar supuestos antes de decisiones materiales."
    return "C", "Evidencia limitada; tratar recomendaciones como hipótesis a validar."


def _find_project_column(df):
    aliases = [
        "nombre_proyecto", "proyecto", "codigo_proyecto", "project",
        "project_name", "project_code"
    ]
    normalized = {_norm_name(c): c for c in df.columns}
    for a in aliases:
        if a in normalized:
            return normalized[a]
    for c in df.columns:
        lc = _norm_name(c)
        if "proyecto" in lc or "project" in lc:
            return c
    return None


def _candidate_metric_columns(df):
    tokens = [
        "venta", "ventas", "minuta", "separ", "absor", "stock", "ritmo",
        "forecast", "wape", "precio", "descuento", "monto", "revenue",
        "conversion", "lead", "gap", "cobertura", "meses", "aging"
    ]
    out = []
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        lc = _norm_name(c)
        if any(t in lc for t in tokens):
            out.append(c)
    return out[:8]


def discover_project_signals(root: Path, fresh_files: list[Path] | None = None, max_projects=5):
    """
    Busca evidencia por proyecto en CSV/XLSX recién generados.
    No inventa métricas: sólo usa columnas realmente presentes.
    """
    candidates = []
    files = fresh_files or []

    if not files:
        for rel in [
            "artifacts/medallio_ceo_briefing",
            "artifacts/medallio_enterprise",
            "artifacts/medallio_ai_factory",
        ]:
            d = root / rel
            if d.exists():
                files.extend([p for p in d.rglob("*") if p.suffix.lower() in {".csv", ".xlsx"}])

    for p in files:
        try:
            if p.suffix.lower() == ".csv":
                df = pd.read_csv(p, nrows=5000)
            elif p.suffix.lower() == ".xlsx":
                df = pd.read_excel(p, nrows=5000)
            else:
                continue
        except Exception:
            continue

        project_col = _find_project_column(df)
        if not project_col:
            continue

        metric_cols = _candidate_metric_columns(df)
        if not metric_cols:
            continue

        work = df[[project_col] + metric_cols].copy()
        work[project_col] = work[project_col].astype("string")
        for c in metric_cols:
            work[c] = pd.to_numeric(work[c], errors="coerce")

        agg = work.groupby(project_col, dropna=True)[metric_cols].mean(numeric_only=True)
        if agg.empty:
            continue

        for project, row in agg.iterrows():
            vals = {}
            for c in metric_cols:
                v = row.get(c)
                if pd.notna(v):
                    vals[c] = float(v)
            if vals:
                candidates.append({
                    "project": str(project),
                    "source": p.name,
                    "metrics": vals,
                })

    # Dedupe by project; prefer records with more metrics.
    best = {}
    for item in candidates:
        key = item["project"]
        if key not in best or len(item["metrics"]) > len(best[key]["metrics"]):
            best[key] = item

    records = list(best.values())
    records.sort(key=lambda x: len(x["metrics"]), reverse=True)
    return records[:max_projects]


def project_signal_sentence(record: dict) -> str:
    pieces = []
    for c, v in list(record.get("metrics", {}).items())[:3]:
        lc = _norm_name(c)
        if any(t in lc for t in ["precio", "monto", "revenue"]):
            pieces.append(f"{c}: {v:,.0f}")
        elif any(t in lc for t in ["conversion", "absor", "wape", "descuento"]):
            pieces.append(f"{c}: {v:.1f}")
        else:
            pieces.append(f"{c}: {v:.1f}")
    detail = " | ".join(pieces) if pieces else "sin métricas comparables"
    return f"{record['project']}: {detail}"


def build_area_recommendations(digest: dict, project_signals: list[dict]) -> dict:
    s = digest["summary"]
    severity = digest.get("severity", "normal")
    open_actions = int(s.get("open_actions") or 0)
    alerts = int(s.get("risk_alerts") or 0)
    wape = s.get("forecast_wape_pct")
    trust = s.get("trust_score_pct")

    recs = {
        "Comercial": [],
        "Pricing": [],
        "Operaciones": [],
        "Marketing": [],
    }

    if open_actions > 0:
        recs["Comercial"].append(
            f"Cerrar {open_actions} acciones abiertas con owner, plazo y criterio de éxito."
        )
    else:
        recs["Comercial"].append(
            "Mantener disciplina del funnel y convertir señales en acciones sólo cuando sean materiales."
        )

    try:
        if wape is not None and float(wape) >= 25:
            recs["Comercial"].append(
                "No usar el forecast como compromiso de meta sin challenger y revisión por proyecto."
            )
    except Exception:
        pass

    if project_signals:
        recs["Pricing"].append(
            "Revisar proyectos con señales de stock/precio/absorción antes de aplicar incrementos generalizados."
        )
    else:
        recs["Pricing"].append(
            "Mantener pricing como hipótesis controlada hasta contar con evidencia por proyecto y tipología."
        )

    if alerts > 0:
        recs["Operaciones"].append(
            f"Resolver {alerts} alerta(s) antes de promover nuevas automatizaciones."
        )
    else:
        recs["Operaciones"].append(
            "Mantener observabilidad, freshness y trazabilidad como condición de operación."
        )

    try:
        if trust is not None and float(trust) < 70:
            recs["Operaciones"].append(
                "Elevar Trust Score antes de automatizar decisiones con impacto económico."
            )
    except Exception:
        pass

    recs["Marketing"].append(
        "Priorizar aprendizaje incremental: canal → lead → separación → minuta → valor económico."
    )
    if severity in {"high", "critical"}:
        recs["Marketing"].append(
            "Evitar ampliar inversión por volumen si no mejora conversión o valor esperado."
        )

    return recs


def build_client_internal_narrative(
    digest: dict,
    project_signals: list[dict],
    area_recs: dict,
) -> dict:
    grade, grade_note = evidence_grade(digest)
    s = digest["summary"]
    project_text = (
        "; ".join(project_signal_sentence(x) for x in project_signals[:3])
        if project_signals else
        "Aún no hay una tabla por proyecto con evidencia suficiente en los artifacts de esta corrida."
    )

    client = [
        f"Lectura: {safe_text(digest.get('headline'))}",
        f"Nivel de evidencia: {grade}. {grade_note}",
        f"Proyectos: {project_text}",
        "Recomendación: concentrar atención en cambios materiales, impacto económico y capacidad de ejecución.",
    ]

    internal = [
        "Convertir cada recomendación en owner + deadline + métrica de éxito.",
        "Separar evidencia descriptiva, predictiva y causal antes de tomar decisiones irreversibles.",
        "Registrar outcome de la acción para que Medallio aprenda qué recomendaciones realmente crean valor.",
        "No escalar automatización si los controles de datos/modelo no cumplen el gate mínimo.",
    ]

    return {"client": client, "internal": internal, "grade": grade}


def build_slot_story(
    root: Path,
    digest: dict,
    links: dict,
    fresh_files: list[Path] | None = None,
) -> dict:
    s = digest["summary"]
    headline = safe_text(digest.get("headline"), "Resumen ejecutivo no disponible")

    changes = digest.get("changes") or []
    if not changes:
        changes = ["Sin cambios materiales frente al briefing anterior."]

    decisions = []
    for d in digest.get("decisions", [])[:3]:
        title = safe_text(d.get("decision") or d.get("signal"), "Mantener rumbo")
        why = safe_text(d.get("why") or d.get("evidence"), "Sin evidencia adicional")
        owner = safe_text(d.get("owner"), "AI Steering Committee")
        decisions.append(f"{title} — {why} · {owner}")
    if not decisions:
        decisions = ["Mantener rumbo y seguir capturando evidencia de valor."]

    severity = digest.get("severity", "normal")
    coverage = fmt_metric(s.get("platform_coverage_pct"), pct=True)
    wape = fmt_metric(s.get("forecast_wape_pct"), pct=True)
    trust = fmt_metric(s.get("trust_score_pct"), pct=True)
    alerts = fmt_metric(s.get("risk_alerts"), pct=False, default="0")
    actions = fmt_metric(s.get("open_actions"), pct=False, default="0")

    grade, grade_note = evidence_grade(digest)
    v27 = digest.get("v27") or {}
    v28 = digest.get("v28") or {}
    gate_summary = v27.get("gate_summary") or {}
    gates = v27.get("gates") or []
    project_signals = discover_project_signals(root, fresh_files=fresh_files, max_projects=5)
    area_recs = build_area_recommendations(digest, project_signals)
    dual = build_client_internal_narrative(digest, project_signals, area_recs)

    if severity == "critical":
        conclusion = (
            "Intervención inmediata: revisar supuestos, validar forecast y concentrar "
            "capacidad gerencial en las decisiones con mayor valor en riesgo."
        )
    elif severity == "high":
        conclusion = (
            "Corrección focalizada: priorizar proyectos, acciones y supuestos con "
            "mayor impacto comercial y evidencia verificable."
        )
    elif severity == "medium":
        conclusion = (
            "Ajustes finos: existen cambios materiales, pero la respuesta debe ser "
            "proporcional a su valor económico y nivel de evidencia."
        )
    else:
        conclusion = (
            "Operación estable: mantener disciplina, convertir insights en outcomes "
            "y elevar la calidad de evidencia antes de automatizar más decisiones."
        )

    client_explanation = [
        f"Lectura ejecutiva: {headline}",
        f"Salud analítica: cobertura {coverage}, confianza {trust}, WAPE {wape}.",
        f"Control: {alerts} alertas y {actions} acciones abiertas.",
        f"Rigor de evidencia: grado {grade}. {grade_note}",
        (
            f"Growth Altitude: L{gate_summary.get('growth_altitude_level', 0)} "
            f"{gate_summary.get('growth_altitude_label', '')}; "
            f"siguiente gate: {gate_summary.get('next_gate_level') or 'máxima altitud'}."
        ),
    ]

    evidence = [
        f"Artifact Vault: {links.get('drive') or 'pendiente'}",
        f"Executive Register: {links.get('sheets') or 'pendiente'}",
        f"CEO Briefing: {links.get('slides') or 'pendiente'}",
        f"Weekly Memo: {links.get('docs') or 'se actualiza en Evening'}",
    ]

    return {
        "headline": headline,
        "changes": changes[:4],
        "decisions": decisions[:3],
        "conclusion": conclusion,
        "client_explanation": client_explanation,
        "evidence": evidence,
        "metrics": {
            "coverage": coverage,
            "wape": wape,
            "trust": trust,
            "alerts": alerts,
            "actions": actions,
        },
        "evidence_grade": grade,
        "project_signals": project_signals,
        "area_recommendations": area_recs,
        "dual_narrative": dual,
        "gate_summary": gate_summary,
        "gates": gates,
        "decision_outcome_gap": v27.get("decision_outcome_gap", []),
        "predictive_gate": v28.get("gate") or {},
        "predictive_performance": v28.get("performance") or [],
        "defensible_forecasts": v28.get("defensible") or [],
        "predictive_factory": v28.get("factory_summary") or {},
        "predictive_maturity_clock": v28.get("maturity_clock") or [],
        "predictive_capture": v28.get("capture") or {},
        "predictive_gate_version": v28.get("gate_version"),
        "predictive_runtime_status": v28.get("status"),
    }


def update_slides(
    root: Path,
    cfg: dict,
    services: dict,
    digest: dict,
    links: dict,
    slot: str,
    fresh_files: list[Path] | None = None,
) -> str | None:
    if (
        not cfg["google"]["slides"]["enabled"]
        or slot not in cfg["communication_policy"]["slides_update_slots"]
    ):
        return google_assets(root, cfg).get("slides_url")

    slides = services["slides"]
    assets = google_assets(root, cfg)
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"slides_{today}"
    pid = assets.get(key)

    if not pid:
        res = slides.presentations().create(
            body={"title": f"{cfg['google']['slides']['presentation_prefix']} {today}"}
        ).execute()
        pid = res["presentationId"]
        assets[key] = pid
        assets["slides_url"] = f"https://docs.google.com/presentation/d/{pid}"
        save_google_assets(root, cfg, assets)

    story = build_slot_story(root, digest, links, fresh_files=fresh_files)
    sev_color = severity_color(digest.get("severity", "normal"))
    grade = story["evidence_grade"]

    # Stable slot IDs are desirable, but Google Slides requires objectId uniqueness.
    # Remove this slot's previous eight pages first, then recreate them.
    slot_slide_ids = [
        f"s_{stable_hash({'date': today, 'slot': slot, 'page': page})[:10]}"
        for page in range(1, 9)
    ]
    try:
        current_presentation = slides.presentations().get(
            presentationId=pid
        ).execute()
        existing_ids = {
            page.get("objectId")
            for page in current_presentation.get("slides", [])
        }
        delete_requests = [
            {"deleteObject": {"objectId": object_id}}
            for object_id in slot_slide_ids
            if object_id in existing_ids
        ]
        if delete_requests:
            slides.presentations().batchUpdate(
                presentationId=pid,
                body={"requests": delete_requests},
            ).execute()
            logging.info(
                "Slides | reemplazando %s páginas previas del slot=%s",
                len(delete_requests),
                slot,
            )
    except Exception as exc:
        logging.warning("Slides | no se pudo limpiar slot previo: %s", exc)

    req = []

    # -----------------------------------------------------------------
    # Slide 1 — Executive Board
    # -----------------------------------------------------------------
    s1 = slot_slide_ids[0]
    req += [{"createSlide": {"objectId": s1, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s1, f"bar_{s1}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s1, f"title_{s1}", f"Medallio · {slot.title()} Executive Brief",
        24, 6, 370, 24, font_size=18, bold=True, color=BRAND["white"]
    )
    req += slide_textbox(
        s1, f"time_{s1}", f"{datetime.now():%H:%M} · Evidence Grade {grade}",
        500, 8, 190, 20, font_size=10, color=BRAND["white"], align="END"
    )
    req += slide_textbox(
        s1, f"headline_{s1}", story["headline"],
        32, 58, 650, 42, font_size=23, bold=True, color=BRAND["navy"]
    )

    labels = ["Coverage", "WAPE", "Trust", "Alerts", "Open Actions"]
    values = [
        story["metrics"]["coverage"],
        story["metrics"]["wape"],
        story["metrics"]["trust"],
        story["metrics"]["alerts"],
        story["metrics"]["actions"],
    ]
    xs = [32, 168, 304, 440, 576]
    colors = [BRAND["blue"], sev_color, BRAND["green"], sev_color, BRAND["navy"]]
    for i, (lab, val, x, col) in enumerate(zip(labels, values, xs, colors), start=1):
        req += kpi_card_requests(s1, f"{s1}_{i}", lab, val, x, 118, col)

    req += slide_rect(s1, f"msgbox_{s1}", 32, 215, 656, 125, BRAND["white"], BRAND["sky"])
    req += slide_textbox(
        s1, f"msg_{s1}",
        bullet_block("Lectura ejecutiva", story["client_explanation"]),
        48, 230, 625, 100, font_size=13, color=BRAND["navy"]
    )

    # -----------------------------------------------------------------
    # Slide 2 — What changed / why it matters
    # -----------------------------------------------------------------
    s2 = slot_slide_ids[1]
    req += [{"createSlide": {"objectId": s2, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s2, f"bar_{s2}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s2, f"title_{s2}", "Qué cambió y por qué importa",
        24, 6, 360, 24, font_size=18, bold=True, color=BRAND["white"]
    )
    req += slide_rect(s2, f"left_{s2}", 30, 64, 310, 255, BRAND["white"], BRAND["sky"])
    req += slide_rect(s2, f"right_{s2}", 365, 64, 325, 255, BRAND["white"], BRAND["sky"])
    req += slide_textbox(
        s2, f"changes_{s2}", bullet_block("Cambios materiales", story["changes"]),
        46, 80, 280, 210, font_size=14, color=BRAND["navy"]
    )
    req += slide_textbox(
        s2, f"decisions_{s2}",
        bullet_block("Decisiones sugeridas", story["decisions"] + [story["conclusion"]]),
        381, 80, 295, 210, font_size=14, color=BRAND["navy"]
    )

    # -----------------------------------------------------------------
    # Slide 3 — Project portfolio
    # -----------------------------------------------------------------
    s3 = slot_slide_ids[2]
    req += [{"createSlide": {"objectId": s3, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s3, f"bar_{s3}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s3, f"title_{s3}", "Portafolio de proyectos · señales observables",
        24, 6, 430, 24, font_size=18, bold=True, color=BRAND["white"]
    )
    if story["project_signals"]:
        project_lines = [project_signal_sentence(x) for x in story["project_signals"][:5]]
        project_note = (
            "Lectura: priorizar proyectos con mayor combinación de stock, absorción, "
            "pricing, forecast o gap — según las métricas disponibles en los artifacts."
        )
    else:
        project_lines = [
            "No se detectó todavía un artifact tabular por proyecto con métricas comparables.",
            "Acción: asegurar export de stock, ventas, absorción, precio, forecast y gap por proyecto.",
        ]
        project_note = "Disciplina: no fabricar conclusiones por proyecto sin evidencia trazable."

    req += slide_rect(s3, f"portfolio_{s3}", 30, 64, 660, 190, BRAND["white"], BRAND["sky"])
    req += slide_textbox(
        s3, f"portfolio_txt_{s3}", bullet_block("Señales por proyecto", project_lines),
        48, 80, 625, 155, font_size=13, color=BRAND["navy"]
    )
    req += slide_rect(s3, f"note_{s3}", 30, 270, 660, 70, BRAND["light"], BRAND["sky"])
    req += slide_textbox(
        s3, f"note_txt_{s3}", project_note,
        46, 286, 630, 44, font_size=13, bold=True, color=BRAND["gray"]
    )

    # -----------------------------------------------------------------
    # Slide 4 — Recommendations by business front
    # -----------------------------------------------------------------
    s4 = slot_slide_ids[3]
    req += [{"createSlide": {"objectId": s4, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s4, f"bar_{s4}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s4, f"title_{s4}", "Recomendaciones por frente de gestión",
        24, 6, 430, 24, font_size=18, bold=True, color=BRAND["white"]
    )

    boxes = [
        ("Comercial", 30, 65, story["area_recommendations"]["Comercial"]),
        ("Pricing", 365, 65, story["area_recommendations"]["Pricing"]),
        ("Operaciones", 30, 205, story["area_recommendations"]["Operaciones"]),
        ("Marketing", 365, 205, story["area_recommendations"]["Marketing"]),
    ]
    for idx, (name, x, y, items) in enumerate(boxes, start=1):
        req += slide_rect(s4, f"box_{s4}_{idx}", x, y, 325, 115, BRAND["white"], BRAND["sky"])
        req += slide_textbox(
            s4, f"txt_{s4}_{idx}", bullet_block(name, items),
            x + 14, y + 12, 295, 88, font_size=12, color=BRAND["navy"]
        )

    # -----------------------------------------------------------------
    # Slide 5 — Client narrative vs internal execution
    # -----------------------------------------------------------------
    s5 = slot_slide_ids[4]
    req += [{"createSlide": {"objectId": s5, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s5, f"bar_{s5}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s5, f"title_{s5}", "Narrativa cliente vs ejecución interna",
        24, 6, 420, 24, font_size=18, bold=True, color=BRAND["white"]
    )
    req += slide_rect(s5, f"client_{s5}", 30, 65, 320, 250, BRAND["white"], BRAND["sky"])
    req += slide_rect(s5, f"internal_{s5}", 370, 65, 320, 250, BRAND["white"], BRAND["sky"])
    req += slide_textbox(
        s5, f"client_txt_{s5}",
        bullet_block("Qué le diría al cliente / Dirección", story["dual_narrative"]["client"]),
        46, 82, 288, 215, font_size=13, color=BRAND["navy"]
    )
    req += slide_textbox(
        s5, f"internal_txt_{s5}",
        bullet_block("Qué debe hacer el equipo interno", story["dual_narrative"]["internal"]),
        386, 82, 288, 215, font_size=13, color=BRAND["navy"]
    )

    # -----------------------------------------------------------------
    # Slide 6 — Evidence / next steps / economic discipline
    # -----------------------------------------------------------------
    s6 = slot_slide_ids[5]
    req += [{"createSlide": {"objectId": s6, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s6, f"bar_{s6}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s6, f"title_{s6}", "Evidence & Outcome Gate · disciplina antes de escalar",
        24, 6, 450, 24, font_size=18, bold=True, color=BRAND["white"]
    )
    req += slide_rect(s6, f"discipline_{s6}", 30, 65, 320, 250, BRAND["white"], BRAND["sky"])
    req += slide_rect(s6, f"evidence_{s6}", 370, 65, 320, 250, BRAND["white"], BRAND["sky"])

    gate_lines = [
        (
            f"L{g.get('level_number')} {g.get('gate_name')}: "
            f"{g.get('gate_status')} — {g.get('reason')}"
        )
        for g in story.get("gates", [])[:7]
    ]
    discipline = gate_lines or [
        f"Evidence Grade: {grade}.",
        "No se encontró un registro de gates para esta corrida."
    ]
    req += slide_textbox(
        s6, f"discipline_txt_{s6}",
        bullet_block("Gates de evidencia", discipline),
        46, 82, 288, 215, font_size=12, color=BRAND["navy"]
    )
    req += slide_textbox(
        s6, f"evidence_txt_{s6}",
        bullet_block("Outcome / siguiente evidencia", [x.get("next_required_step") for x in story.get("decision_outcome_gap", [])[:4]] or story["evidence"]),
        386, 82, 288, 215, font_size=12, color=BRAND["navy"]
    )


    # -----------------------------------------------------------------
    # Slide 7 — Forecasts we can defend
    # -----------------------------------------------------------------
    s7 = slot_slide_ids[6]
    req += [{"createSlide": {"objectId": s7, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s7, f"bar_{s7}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s7, f"title_{s7}", "Predicciones que ya podemos defender",
        24, 6, 430, 24, font_size=18, bold=True, color=BRAND["white"]
    )

    pg = story.get("predictive_gate") or {}
    pg_status = safe_text(pg.get("gate_status"), "BLOCK")
    mature_pairs = fmt_metric(pg.get("mature_pairs"), pct=False, default="0")
    projects_mature = fmt_metric(pg.get("projects_with_mature"), pct=False, default="0")
    mature_wape = fmt_metric(pg.get("global_wape_pct"), pct=True, default="N/A")
    mature_bias = fmt_metric(pg.get("global_bias_pct"), pct=True, default="N/A")
    defend_cells = fmt_metric(pg.get("defensible_cells"), pct=False, default="0")

    p_labels = ["Gate L3", "Pares maduros", "Proyectos", "WAPE", "Bias"]
    p_values = [pg_status, mature_pairs, projects_mature, mature_wape, mature_bias]
    p_xs = [32, 168, 304, 440, 576]
    for i, (lab, val, x) in enumerate(zip(p_labels, p_values, p_xs), start=1):
        req += kpi_card_requests(s7, f"{s7}_{i}", lab, val, x, 65, BRAND["blue"])

    defendible = story.get("defensible_forecasts") or []
    perf = story.get("predictive_performance") or []

    if defendible:
        defend_lines = [
            (
                f"{r.get('project_key')} · H{r.get('horizon')} · "
                f"n={r.get('mature_pairs')} · "
                f"WAPE={fmt_metric(r.get('wape_pct'), pct=True)} · "
                f"Bias={fmt_metric(r.get('bias_pct'), pct=True)}"
            )
            for r in defendible[:5]
        ]
    else:
        defend_lines = [
            "Aún no hay una celda proyecto×horizonte que cumpla todos los criterios.",
            "Medallio no convierte existencia de modelo en evidencia predictiva.",
        ]

    watch_rows = [r for r in perf if str(r.get("defense_status")) != "DEFENSIBLE"]
    if watch_rows:
        watch_lines = [
            (
                f"{r.get('project_key')} · H{r.get('horizon')} · "
                f"{r.get('defense_status')} · n={r.get('mature_pairs')} · "
                f"WAPE={fmt_metric(r.get('wape_pct'), pct=True)}"
            )
            for r in watch_rows[:4]
        ]
    else:
        watch_lines = [safe_text(pg.get("gate_reason"), "Sin brechas predictivas adicionales.")]

    req += slide_rect(s7, f"left_{s7}", 30, 155, 320, 165, BRAND["white"], BRAND["sky"])
    req += slide_rect(s7, f"right_{s7}", 370, 155, 320, 165, BRAND["white"], BRAND["sky"])

    req += slide_textbox(
        s7, f"left_txt_{s7}",
        bullet_block(f"Defendibles · {defend_cells} celdas", defend_lines),
        46, 170, 288, 132, font_size=12, color=BRAND["navy"]
    )
    req += slide_textbox(
        s7, f"right_txt_{s7}",
        bullet_block("No promover todavía", watch_lines),
        386, 170, 288, 132, font_size=12, color=BRAND["navy"]
    )

    req += slide_textbox(
        s7, f"policy_{s7}",
        (
            "Política PASS L3: ≥12 pares maduros · ≥3 proyectos · ≥3 celdas defendibles · "
            "WAPE ≤25% · |Bias| ≤15% · 100% leakage-safe."
        ),
        35, 330, 650, 28, font_size=10, bold=True, color=BRAND["gray"], align="CENTER"
    )


    # -----------------------------------------------------------------
    # Slide 8 — Predictive Evidence Factory
    # -----------------------------------------------------------------
    s8 = slot_slide_ids[7]
    req += [{"createSlide": {"objectId": s8, "slideLayoutReference": {"predefinedLayout": "BLANK"}}}]
    req += slide_rect(s8, f"bar_{s8}", 0, 0, 720, 40, BRAND["navy"])
    req += slide_textbox(
        s8, f"title_{s8}", "Predictive Evidence Factory · emisión → madurez → benchmark",
        24, 6, 560, 24, font_size=18, bold=True, color=BRAND["white"]
    )

    pf = story.get("predictive_factory") or {}
    issued = fmt_metric(pf.get("issued_total"), default="0")
    incubating = fmt_metric(pf.get("incubating"), default="0")
    evaluated = fmt_metric(pf.get("evaluated"), default="0")
    next_maturity = safe_text(pf.get("next_maturity_date"), "pendiente")
    skill = fmt_metric(pf.get("skill_vs_naive_pct"), pct=True, default="N/A")

    labels = ["Emitidos", "Incubando", "Evaluados", "Próxima madurez", "Skill vs naïve"]
    values = [issued, incubating, evaluated, next_maturity, skill]
    xs = [32, 168, 304, 440, 576]
    for i, (lab, val, x) in enumerate(zip(labels, values, xs), start=1):
        req += kpi_card_requests(s8, f"{s8}_{i}", lab, val, x, 65, BRAND["blue"])

    capture = story.get("predictive_capture") or {}
    pipeline_lines = [
        f"Última captura: {capture.get('status') or '-'}",
        f"Celdas candidatas: {capture.get('candidate_cells') or 0}",
        f"Nuevas emisiones: {capture.get('inserted') or 0}",
        f"Sin cambio: {capture.get('unchanged') or 0}",
        f"Ambiguas: {capture.get('ambiguous_cells') or 0}",
    ]

    benchmark_lines = [
        f"Benchmark activo: {pf.get('benchmarked_active') or 0}",
        f"WAPE modelo: {fmt_metric(pf.get('global_wape_pct'), pct=True)}",
        f"WAPE naïve: {fmt_metric(pf.get('naive_wape_pct'), pct=True)}",
        f"Beat rate: {fmt_metric(pf.get('model_beat_rate_pct'), pct=True)}",
        f"Gate: {safe_text(pf.get('gate_status'), 'BLOCK')}",
    ]

    req += slide_rect(s8, f"left_{s8}", 30, 155, 320, 165, BRAND["white"], BRAND["sky"])
    req += slide_rect(s8, f"right_{s8}", 370, 155, 320, 165, BRAND["white"], BRAND["sky"])
    req += slide_textbox(
        s8, f"left_txt_{s8}", bullet_block("Registro prospectivo", pipeline_lines),
        46, 170, 288, 132, font_size=12, color=BRAND["navy"]
    )
    req += slide_textbox(
        s8, f"right_txt_{s8}", bullet_block("Disciplina benchmark", benchmark_lines),
        386, 170, 288, 132, font_size=12, color=BRAND["navy"]
    )
    req += slide_textbox(
        s8, f"policy_{s8}",
        "Una predicción no se evalúa hasta que el target cierre; L3 PASS además exige superar el benchmark naïve congelado al emitir.",
        35, 330, 650, 28, font_size=10, bold=True, color=BRAND["gray"], align="CENTER"
    )

    try:
        slides.presentations().batchUpdate(
            presentationId=pid,
            body={"requests": req},
        ).execute()
    except Exception as exc:
        logging.warning("Slides omitido: %s", exc)

    return assets.get("slides_url") or f"https://docs.google.com/presentation/d/{pid}"


# ---------------------------------------------------------------------
# DOCS WEEKLY MEMO
# ---------------------------------------------------------------------

def update_weekly_doc(
    root: Path,
    cfg: dict,
    services: dict,
    digest: dict,
    links: dict,
    slot: str,
) -> str | None:
    if not cfg["google"]["docs"]["enabled"]:
        return None

    # El memo semanal sólo se actualiza en Evening.
    # Morning/Midday no deben depender de Google Docs.
    assets = google_assets(root, cfg)
    if slot != "evening":
        return assets.get("docs_url")

    docs = services["docs"]
    week = datetime.now().strftime("%G-W%V")
    key = f"docs_{week}"
    did = assets.get(key)

    if not did:
        res = docs.documents().create(
            body={
                "title": f"{cfg['google']['docs']['weekly_memo_prefix']} {week}"
            }
        ).execute()
        did = res["documentId"]
        assets[key] = did
        assets["docs_url"] = f"https://docs.google.com/document/d/{did}"
        save_google_assets(root, cfg, assets)

    doc = docs.documents().get(documentId=did).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1

    decisions = "\n".join(
        f"- {d.get('decision', d.get('signal', ''))}"
        for d in digest["decisions"][:5]
    ) or "- Sin decisiones nuevas"

    text = (
        f"\n\n{datetime.now():%Y-%m-%d} Evening Briefing\n"
        f"{digest['headline']}\n"
        f"Severity: {digest['severity']}\n"
        f"Changes: {', '.join(digest['changes']) or 'Sin cambios materiales'}\n"
        f"Decisions:\n{decisions}\n"
        f"Drive: {links.get('drive') or '-'}\n"
        f"Slides: {links.get('slides') or '-'}\n"
    )

    docs.documents().batchUpdate(
        documentId=did,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": text,
                    }
                }
            ]
        },
    ).execute()

    return assets.get("docs_url")


# ---------------------------------------------------------------------
# CALENDAR / CHAT
# ---------------------------------------------------------------------

def severity_rank(value: str) -> int:
    return {
        "normal": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }.get(value, 0)


def calendar_escalation(
    root: Path,
    cfg: dict,
    services: dict,
    digest: dict,
    links: dict,
) -> str | None:
    if not cfg["google"]["calendar"]["enabled"]:
        return None

    minimum = cfg["communication_policy"]["calendar_min_severity"]
    if severity_rank(digest["severity"]) < severity_rank(minimum):
        return None

    payload = {
        "headline": digest["headline"],
        "severity": digest["severity"],
        "decisions": digest["decisions"][:3],
    }
    if seen(root, cfg, "calendar", payload):
        return None

    tz = ZoneInfo(cfg["timezone"])
    start = datetime.now(tz) + timedelta(minutes=30)
    end = start + timedelta(
        minutes=int(cfg["google"]["calendar"]["event_duration_minutes"])
    )

    desc = (
        f"{digest['headline']}\n\n"
        + "\n".join(
            f"- {d.get('decision', d.get('signal', ''))}"
            for d in digest["decisions"][:3]
        )
        + f"\n\nDrive: {links.get('drive') or '-'}"
        + f"\nSlides: {links.get('slides') or '-'}"
    )

    event = {
        "summary": f"[Medallio] Decision Review · {digest['severity'].upper()}",
        "description": desc,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": cfg["timezone"],
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": cfg["timezone"],
        },
        "extendedProperties": {
            "private": {"medallio_fp": stable_hash(payload)}
        },
    }

    res = services["calendar"].events().insert(
        calendarId=cfg["google"]["calendar"]["calendar_id"],
        body=event,
    ).execute()

    mark_seen(root, cfg, "calendar", payload)
    return res.get("htmlLink")


def chat_alert(
    root: Path,
    cfg: dict,
    services: dict,
    digest: dict,
    links: dict,
) -> str | None:
    chat_cfg = cfg["google"]["chat"]
    if not chat_cfg["enabled"] or not chat_cfg.get("space_name"):
        return None

    minimum = cfg["communication_policy"]["chat_min_severity"]
    if severity_rank(digest["severity"]) < severity_rank(minimum):
        return None

    payload = {
        "headline": digest["headline"],
        "severity": digest["severity"],
        "decisions": digest["decisions"][:3],
    }
    if seen(root, cfg, "chat", payload):
        return None

    text = (
        f"⚠️ Medallio {digest['severity'].upper()}\n"
        f"{digest['headline']}\n"
        + "\n".join(
            f"• {d.get('decision', d.get('signal', ''))}"
            for d in digest["decisions"][:3]
        )
        + f"\nDrive: {links.get('drive') or '-'}"
    )

    res = services["chat"].spaces().messages().create(
        parent=chat_cfg["space_name"],
        body={"text": text},
    ).execute()

    mark_seen(root, cfg, "chat", payload)
    return res.get("name")


# ---------------------------------------------------------------------
# GMAIL
# ---------------------------------------------------------------------

def build_email(
    cfg: dict,
    digest: dict,
    links: dict,
    attachments: list[Path],
    slot: str,
) -> EmailMessage:
    s = digest["summary"]
    v27 = digest.get("v27") or {}
    gs = v27.get("gate_summary") or {}
    subject = (
        f"{cfg['subject_prefix']} {slot.title()} | "
        f"L{gs.get('growth_altitude_level', 0)} {gs.get('growth_altitude_label', 'Evidence')} | "
        f"Gate {gs.get('next_gate_level') or 'MAX'} {gs.get('next_gate_status') or ''} | "
        f"{fmt_metric(s.get('open_actions'), pct=False, default='0')} acciones"
    )

    changes = "".join(
        f"<li>{html.escape(str(x))}</li>"
        for x in digest["changes"]
    ) or "<li>Sin cambios materiales.</li>"

    decisions = "".join(
        f"<li><b>{html.escape(str(d.get('decision', d.get('signal', 'Decisión'))))}</b>"
        f" — {html.escape(str(d.get('why', d.get('evidence', ''))))}"
        f"{' · ' + html.escape(str(d.get('owner', ''))) if d.get('owner') else ''}</li>"
        for d in digest["decisions"][:3]
    ) or "<li>Sin decisiones ejecutivas nuevas.</li>"

    link_rows = [
        ("Artifact Vault", links.get("drive")),
        ("Executive Register", links.get("sheets")),
        ("CEO Briefing", links.get("slides")),
        ("Weekly Intelligence Memo", links.get("docs")),
        ("Decision Review", links.get("calendar")),
    ]
    link_html = "".join(
        f"<li><a href='{html.escape(str(url))}'>{html.escape(name)}</a></li>"
        for name, url in link_rows
        if url
    )

    body = f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#222;max-width:900px">
      <h2>Medallio Ambassador · {slot.title()}</h2>
      <p style="font-size:17px"><b>{html.escape(digest['headline'])}</b></p>

      <table style="border-collapse:collapse">
        <tr>
          <td style="padding:9px;border:1px solid #ddd"><b>Coverage</b><br>{fmt_metric(s.get('platform_coverage_pct'), pct=True)}</td>
          <td style="padding:9px;border:1px solid #ddd"><b>WAPE</b><br>{fmt_metric(s.get('forecast_wape_pct'), pct=True)}</td>
          <td style="padding:9px;border:1px solid #ddd"><b>Trust</b><br>{fmt_metric(s.get('trust_score_pct'), pct=True)}</td>
          <td style="padding:9px;border:1px solid #ddd"><b>Alerts</b><br>{s.get('risk_alerts')}</td>
          <td style="padding:9px;border:1px solid #ddd"><b>Actions</b><br>{s.get('open_actions')}</td>
        </tr>
      </table>

      <h3>Evidence & Outcome Gate</h3>
      <p>
        <b>Growth Altitude:</b> L{gs.get('growth_altitude_level', 0)} · {html.escape(str(gs.get('growth_altitude_label', '')))}<br>
        <b>Siguiente gate:</b> {html.escape(str(gs.get('next_gate_level') or 'Máxima altitud'))} ·
        {html.escape(str(gs.get('next_gate_status') or ''))}<br>
        {html.escape(str(gs.get('next_gate_reason') or ''))}
      </p>

      <h3>Predictive Gate · v2.8.3</h3>
      <p>
        <b>Status:</b> {html.escape(str((digest.get('v28') or {}).get('gate', {}).get('gate_status') or 'BLOCK'))}<br>
        <b>Pares maduros:</b> {html.escape(str((digest.get('v28') or {}).get('gate', {}).get('mature_pairs') or 0))} ·
        <b>Proyectos:</b> {html.escape(str((digest.get('v28') or {}).get('gate', {}).get('projects_with_mature') or 0))} ·
        <b>WAPE:</b> {fmt_metric((digest.get('v28') or {}).get('gate', {}).get('global_wape_pct'), pct=True)} ·
        <b>Bias:</b> {fmt_metric((digest.get('v28') or {}).get('gate', {}).get('global_bias_pct'), pct=True)}<br>
        {html.escape(str((digest.get('v28') or {}).get('gate', {}).get('gate_reason') or 'Aún no existe evidencia predictiva madura suficiente.'))}
      </p>

      <h3>Predictive Evidence Factory</h3>
      <p>
        <b>Emitidos:</b> {html.escape(str((digest.get('v28') or {}).get('factory_summary', {}).get('issued_total') or 0))} ·
        <b>Incubando:</b> {html.escape(str((digest.get('v28') or {}).get('factory_summary', {}).get('incubating') or 0))} ·
        <b>Evaluados:</b> {html.escape(str((digest.get('v28') or {}).get('factory_summary', {}).get('evaluated') or 0))} ·
        <b>Próxima madurez:</b> {html.escape(str((digest.get('v28') or {}).get('factory_summary', {}).get('next_maturity_date') or 'pendiente'))}<br>
        <b>Naïve WAPE:</b> {fmt_metric((digest.get('v28') or {}).get('factory_summary', {}).get('naive_wape_pct'), pct=True)} ·
        <b>Skill vs naïve:</b> {fmt_metric((digest.get('v28') or {}).get('factory_summary', {}).get('skill_vs_naive_pct'), pct=True)}
      </p>

      <h3>Desde el briefing anterior</h3>
      <ul>{changes}</ul>

      <h3>Top decisiones</h3>
      <ol>{decisions}</ol>

      <h3>Abrir evidencia</h3>
      <ul>{link_html}</ul>

      <p style="color:#666;font-size:12px">
        Email deliberadamente corto. Drive contiene evidencia; Sheets mantiene memoria;
        Slides comunica; Calendar/Chat sólo escalan señales severas.
      </p>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["To"] = cfg["recipient"]
    msg["Subject"] = subject
    msg["From"] = "Medallio Ambassador"
    msg.set_content("Abre este correo en un cliente compatible con HTML.")
    msg.add_alternative(body, subtype="html")

    for p in attachments:
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        main, sub = ctype.split("/", 1)
        msg.add_attachment(
            p.read_bytes(),
            maintype=main,
            subtype=sub,
            filename=p.name,
        )

    return msg


def send_gmail(gmail, msg: EmailMessage):
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return gmail.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()


# ---------------------------------------------------------------------
# OPTIONAL CLOUD
# ---------------------------------------------------------------------

def publish_pubsub(cfg: dict, payload: dict):
    c = cfg["cloud_optional"]["pubsub"]
    if not c["enabled"]:
        return None

    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic = publisher.topic_path(c["project_id"], c["topic_id"])
    return publisher.publish(
        topic,
        json.dumps(payload, default=str).encode(),
    ).result(timeout=30)


def archive_bigquery(cfg: dict, payload: dict):
    c = cfg["cloud_optional"]["bigquery"]
    if not c["enabled"]:
        return None

    from google.cloud import bigquery

    client = bigquery.Client(project=c["project_id"])
    table = f"{c['project_id']}.{c['dataset_id']}.{c['table_id']}"
    row = dict(payload)
    row["archived_at"] = datetime.utcnow().isoformat() + "Z"
    errors = client.insert_rows_json(table, [row])

    if errors:
        logging.warning("BigQuery archive: %s", errors)
    return errors


# ---------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------

def append_history(
    root: Path,
    cfg: dict,
    slot: str,
    digest: dict,
    email_sent: bool,
    artifacts: list[Path],
    links: dict,
):
    p = root / cfg["paths"]["runtime_dir"] / "run_history_v2.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists()
    s = digest["summary"]

    with p.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow([
                "timestamp",
                "slot",
                "severity",
                "email_sent",
                "artifacts",
                "coverage",
                "wape",
                "trust",
                "drive",
                "sheets",
                "slides",
                "docs",
            ])

        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            slot,
            digest["severity"],
            int(email_sent),
            len(artifacts),
            s.get("platform_coverage_pct"),
            s.get("forecast_wape_pct"),
            s.get("trust_score_pct"),
            links.get("drive"),
            links.get("sheets"),
            links.get("slides"),
            links.get("docs"),
        ])



# ---------------------------------------------------------------------
# CHANNEL FAULT ISOLATION
# ---------------------------------------------------------------------

def safe_channel(name: str, fn, default=None):
    """
    Ejecuta un canal externo sin permitir que una integración secundaria
    derribe todo el briefing. Devuelve (resultado, estado).
    """
    try:
        value = fn()
        logging.info("CHANNEL OK | %s", name)
        return value, "OK"
    except Exception as exc:
        logging.exception("CHANNEL DEGRADED | %s | %s", name, exc)
        return default, f"ERROR:{type(exc).__name__}"


def save_email_outbox(root: Path, cfg: dict, msg: EmailMessage) -> Path:
    d = root / cfg["paths"]["runtime_dir"] / "outbox"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{datetime.now():%Y%m%d_%H%M%S}.eml"
    p.write_bytes(msg.as_bytes())
    logging.warning("Gmail no enviado; mensaje guardado en outbox: %s", p)
    return p


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--slot",
        choices=["morning", "midday", "evening"],
        required=True,
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = find_repo_root()
    cfg = load_config(root)
    ensure_runtime(root, cfg)
    setup_logging(root, cfg)

    lock = root / cfg["paths"]["runtime_dir"] / ".lock"

    with FileLock(lock):
        run_started = time.time()
        logging.info("Medallio Ambassador v2 start | slot=%s", args.slot)

        notebook_list = list(cfg["notebooks"]["every_run"])
        if args.slot == "evening":
            notebook_list += list(cfg["notebooks"].get("evening_only", []))

        results = []
        for rel in notebook_list:
            timeout = int(
                cfg["notebook_timeouts_seconds"].get(rel, 1200)
            )
            results.append(
                execute_notebook(
                    root,
                    rel,
                    timeout,
                    cfg["kernel_name"],
                )
            )

        previous = last_summary(root, cfg)
        digest = build_digest(root, results, previous, cfg)

        # v2.8 freezes the forecast before Evidence Gate evaluation.
        digest = refresh_predictive_gate_v28(root, cfg, digest, args.slot, dry_run=args.dry_run)

        initial_fresh = current_run_artifacts(root, cfg, run_started)
        digest = enrich_digest_v27(root, cfg, digest, initial_fresh, args.slot)

        # Re-scan: v2.7 generated new evidence/outcome artifacts.
        fresh = current_run_artifacts(root, cfg, run_started)
        email_files = choose_artifacts(
            fresh,
            int(cfg["communication_policy"]["email_max_attachments"]),
            float(cfg["communication_policy"]["email_attachment_budget_mb"]),
        )
        drive_files = choose_artifacts(
            fresh,
            int(cfg["communication_policy"]["drive_max_artifacts_per_run"]),
            float(cfg["communication_policy"]["drive_max_total_mb_per_run"]),
        )

        if args.dry_run:
            logging.info(
                "DRY RUN | severity=%s | fresh_artifacts=%d | email_attachments=%d",
                digest["severity"],
                len(fresh),
                len(email_files),
            )
            for change in digest["changes"]:
                logging.info("CHANGE | %s", change)
            logging.info("Headline | %s", digest["headline"])
            gs = (digest.get("v27") or {}).get("gate_summary") or {}
            logging.info(
                "V2.7 | altitude=L%s %s | next=%s %s | db_sync=%s",
                gs.get("growth_altitude_level"),
                gs.get("growth_altitude_label"),
                gs.get("next_gate_level"),
                gs.get("next_gate_status"),
                (digest.get("v27") or {}).get("db_sync"),
            )
            return

        creds = google_credentials(root, cfg)
        services = google_services(creds)
        channel_health = {}

        vault, channel_health["drive"] = safe_channel(
            "Drive",
            lambda: upload_drive_vault(
                root, cfg, services, drive_files, args.slot
            ),
            {"folder_url": None, "uploaded": []},
        )
        links = {"drive": (vault or {}).get("folder_url")}

        links["sheets"], channel_health["sheets"] = safe_channel(
            "Sheets",
            lambda: update_sheets_memory(
                root, cfg, services, digest, (vault or {}).get("uploaded", []), args.slot
            ),
            None,
        )

        links["slides"], channel_health["slides"] = safe_channel(
            "Slides",
            lambda: update_slides(
                root, cfg, services, digest, links, args.slot, fresh_files=fresh
            ),
            None,
        )

        links["docs"], channel_health["docs"] = safe_channel(
            "Docs",
            lambda: update_weekly_doc(
                root, cfg, services, digest, links, args.slot
            ),
            None,
        )

        links["calendar"], channel_health["calendar"] = safe_channel(
            "Calendar",
            lambda: calendar_escalation(
                root, cfg, services, digest, links
            ),
            None,
        )

        links["chat"], channel_health["chat"] = safe_channel(
            "Chat",
            lambda: chat_alert(
                root, cfg, services, digest, links
            ),
            None,
        )

        degraded = [k for k, v in channel_health.items() if not str(v).startswith("OK")]
        if degraded:
            digest["changes"] = (
                [f"Canales degradados: {', '.join(degraded)}"] + digest["changes"]
            )[:5]

        msg = build_email(
            cfg,
            digest,
            links,
            email_files,
            args.slot,
        )

        response, channel_health["gmail"] = safe_channel(
            "Gmail",
            lambda: send_gmail(services["gmail"], msg),
            None,
        )
        if response:
            logging.info(
                "Gmail enviado | message_id=%s | adjuntos=%d",
                response.get("id"),
                len(email_files),
            )
            email_sent = True
        else:
            save_email_outbox(root, cfg, msg)
            email_sent = False

        cloud_payload = {
            "slot": args.slot,
            "severity": digest["severity"],
            "headline": digest["headline"],
            **digest["summary"],
            "links": links,
        }

        try:
            publish_pubsub(cfg, cloud_payload)
        except Exception:
            logging.exception("Pub/Sub opcional falló")

        try:
            archive_bigquery(cfg, cloud_payload)
        except Exception:
            logging.exception("BigQuery opcional falló")

        save_last_summary(root, cfg, digest["summary"])
        append_history(
            root,
            cfg,
            args.slot,
            digest,
            email_sent,
            email_files,
            links,
        )

        logging.info("Medallio Ambassador v2 end")


if __name__ == "__main__":
    main()
