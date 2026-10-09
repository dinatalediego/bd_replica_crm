from __future__ import annotations

import argparse
import base64
import csv
import json
import logging
import mimetypes
import os
import shutil
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
from jupyter_client.kernelspec import KernelSpecManager
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def find_repo_root() -> Path:
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / ".env.example").exists():
            return candidate
    return p

def load_config(root: Path) -> dict:
    path = root / "config" / "medallio_ambassador.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} no existe. Copia medallio_ambassador.example.json y configura recipient."
        )
    return json.loads(path.read_text(encoding="utf-8"))

def setup_logging(root: Path):
    log_dir = root / "artifacts" / "medallio_ambassador" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"{datetime.now():%Y-%m-%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(logfile, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )

class FileLock:
    def __init__(self, path: Path, stale_seconds=4*3600):
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
            raise RuntimeError(f"Ya existe una corrida activa: {self.path}")

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fd is not None:
                os.close(self.fd)
        finally:
            self.path.unlink(missing_ok=True)

def resolve_kernel_name(nb, preferred_kernel: str | None = None) -> str:
    """
    Selecciona un kernel real y registrado.

    Prioridad:
      1) config.kernel_name
      2) metadata del notebook
      3) medallio_dw
      4) python3
    """
    ksm = KernelSpecManager()
    available = ksm.find_kernel_specs()

    metadata_kernel = None
    try:
        metadata_kernel = nb.metadata.get("kernelspec", {}).get("name")
    except Exception:
        metadata_kernel = None

    candidates = []
    # Medallio primero: evita que metadata genérica "python3" gane
    # cuando el kernel corporativo ya está registrado.
    for candidate in [preferred_kernel, "medallio_dw", metadata_kernel, "python3"]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if candidate in available:
            logging.info(
                "Kernel seleccionado: %s | disponibles=%s",
                candidate,
                ", ".join(sorted(available.keys())),
            )
            return candidate

    raise RuntimeError(
        "No se encontró un kernel Jupyter utilizable. "
        f"Candidatos={candidates}; disponibles={sorted(available.keys())}. "
        "Ejecuta: python -m ipykernel install --user "
        "--name medallio_dw --display-name \"Python - Medallio DW\""
    )


def execute_notebook(
    root: Path,
    rel_path: str,
    timeout: int,
    preferred_kernel: str | None = None,
) -> dict:
    nb_path = root / rel_path
    started = datetime.now()
    result = {
        "notebook": rel_path,
        "status": "MISSING",
        "seconds": 0,
        "error": "",
        "kernel": "",
    }
    if not nb_path.exists():
        result["error"] = f"No existe {nb_path}"
        return result

    logging.info("Ejecutando %s", rel_path)
    try:
        nb = nbformat.read(nb_path, as_version=4)
        kernel_name = resolve_kernel_name(nb, preferred_kernel)
        result["kernel"] = kernel_name

        ep = ExecutePreprocessor(
            timeout=timeout,
            startup_timeout=120,
            kernel_name=kernel_name,
            allow_errors=False,
        )
        # Ejecutar desde la raíz para que .env y artifacts sean coherentes.
        ep.preprocess(nb, {"metadata": {"path": str(root)}})
        result["status"] = "OK"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = f"{type(e).__name__}: {e}"
        logging.exception("Notebook falló: %s", rel_path)
    result["seconds"] = round((datetime.now() - started).total_seconds(), 1)
    return result

def artifact_score(path: Path) -> int:
    n = path.name.lower()
    ext = path.suffix.lower()
    score = 0
    keywords = {
        "board_summary": 140,
        "ceo_decision_queue": 135,
        "ceo_control_tower_summary": 130,
        "ceo_confidence": 125,
        "value_at_stake": 120,
        "forecast_confidence": 115,
        "ceo_action_board": 112,
        "ai_portfolio": 110,
        "ceo_heatmap": 108,
        "decision": 100,
        "forecast": 95,
        "value": 92,
        "confidence": 90,
        "ceo": 88,
        "summary": 85,
        "maturity": 75,
        "governance": 70,
        "drift": 68,
    }
    for k, v in keywords.items():
        if k in n:
            score = max(score, v)

    ext_bonus = {".png": 20, ".csv": 15, ".json": 12, ".pdf": 8, ".xlsx": 5}
    score += ext_bonus.get(ext, 0)

    # Muy nuevos = más relevantes.
    age_hours = max(0, (time.time() - path.stat().st_mtime) / 3600)
    if age_hours <= 8:
        score += 20
    elif age_hours <= 24:
        score += 10

    return score

def select_attachments(root: Path, cfg: dict, since_epoch: float | None = None) -> list[Path]:
    budget = int(cfg.get("attachment_budget_mb", 18) * 1024 * 1024)
    max_single = int(cfg.get("max_single_attachment_mb", 7) * 1024 * 1024)

    candidates = []
    for rel_root in cfg.get("artifact_roots", []):
        d = root / rel_root
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".png", ".csv", ".json", ".pdf", ".xlsx"}:
                continue
            stat = p.stat()
            size = stat.st_size
            if size <= 0 or size > max_single:
                continue
            # Evitar enviar artefactos viejos como si pertenecieran a la corrida actual.
            if since_epoch is not None and stat.st_mtime < since_epoch:
                continue
            candidates.append((artifact_score(p), stat.st_mtime, size, p))

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

    selected = []
    used = 0
    for score, mtime, size, p in candidates:
        if used + size > budget:
            continue
        selected.append(p)
        used += size

    logging.info("Adjuntos seleccionados: %d archivos, %.2f MiB", len(selected), used/1024/1024)
    return selected

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def read_csv_records(path: Path, max_rows=5):
    try:
        import pandas as pd
        return pd.read_csv(path).head(max_rows).to_dict("records")
    except Exception:
        return []

def latest_board_summary(root: Path, since_epoch: float | None = None):
    p = root / "artifacts" / "medallio_ceo_briefing" / "board_summary.json"
    if not p.exists():
        return None
    if since_epoch is not None and p.stat().st_mtime < since_epoch:
        return None
    return read_json(p)

def latest_decisions(root: Path, since_epoch: float | None = None):
    p = root / "artifacts" / "medallio_ceo_briefing" / "ceo_decision_queue.csv"
    if not p.exists():
        return []
    if since_epoch is not None and p.stat().st_mtime < since_epoch:
        return []
    return read_csv_records(p, 5)

def html_escape(x):
    import html
    return html.escape("" if x is None else str(x))

def build_email_html(slot: str, results: list[dict], board: dict | None, decisions: list[dict]) -> str:
    ok = sum(r["status"] == "OK" for r in results)
    err = sum(r["status"] == "ERROR" for r in results)

    rows = "".join(
        f"<tr><td>{html_escape(Path(r['notebook']).name)}</td>"
        f"<td>{html_escape(r['status'])}</td>"
        f"<td>{html_escape(r['seconds'])}s</td></tr>"
        for r in results
    )

    metrics = ""
    if board:
        pairs = [
            ("Cobertura", board.get("platform_coverage_pct")),
            ("Forecast WAPE", board.get("forecast_wape_pct")),
            ("Bias", board.get("forecast_bias")),
            ("Acciones abiertas", board.get("open_actions")),
            ("Alertas", board.get("risk_alerts")),
            ("Outcomes", board.get("outcomes")),
            ("Trust score", board.get("trust_score_pct")),
        ]
        items = "".join(
            f"<td style='padding:10px;border:1px solid #ddd'><b>{html_escape(k)}</b><br>{html_escape(v)}</td>"
            for k, v in pairs
        )
        metrics = f"<table style='border-collapse:collapse'><tr>{items}</tr></table>"

    decision_html = "<p>Sin decisiones ejecutivas registradas.</p>"
    if decisions:
        items = []
        for d in decisions[:5]:
            decision = d.get("decision", d.get("signal", "Decisión"))
            why = d.get("why", d.get("evidence", ""))
            owner = d.get("owner", "")
            items.append(
                f"<li><b>{html_escape(decision)}</b>"
                f" — {html_escape(why)}"
                f"{' · ' + html_escape(owner) if owner else ''}</li>"
            )
        decision_html = "<ol>" + "".join(items) + "</ol>"

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#222">
      <h2>Medallio Ambassador — {html_escape(slot.title())}</h2>
      <p><b>{datetime.now():%Y-%m-%d %H:%M}</b> · {ok} notebooks OK · {err} con error.</p>

      <h3>CEO Signal</h3>
      {metrics or '<p>Board summary aún no disponible.</p>'}

      <h3>Decisiones prioritarias</h3>
      {decision_html}

      <h3>Ejecución</h3>
      <table style="border-collapse:collapse">
        <tr><th style="text-align:left;padding:6px">Notebook</th>
            <th style="text-align:left;padding:6px">Estado</th>
            <th style="text-align:left;padding:6px">Duración</th></tr>
        {rows}
      </table>

      <p style="margin-top:18px;color:#666;font-size:12px">
        Medallio Ambassador prioriza artefactos ejecutivos por valor y peso.
        Los adjuntos se mantienen bajo un presupuesto configurable para evitar correos pesados.
      </p>
    </body></html>
    """

def gmail_credentials(root: Path, cfg: dict):
    token_path = root / cfg["gmail"]["token_file"]
    if not token_path.exists():
        raise FileNotFoundError(
            f"No existe {token_path}. Ejecuta gmail_oauth_setup.py una sola vez."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds

def make_message(cfg: dict, slot: str, html_body: str, attachments: Iterable[Path], subject_metrics: dict | None):
    recipient = cfg["recipient"]
    if not recipient or recipient.startswith("TU_CORREO"):
        raise ValueError("Configura recipient en config/medallio_ambassador.json")

    subject = f"{cfg.get('subject_prefix','[Medallio Ambassador]')} {slot.title()}"
    if subject_metrics:
        c = subject_metrics.get("platform_coverage_pct")
        w = subject_metrics.get("forecast_wape_pct")
        a = subject_metrics.get("open_actions")
        suffix = []
        if c is not None: suffix.append(f"Coverage {c}%")
        if w is not None: suffix.append(f"WAPE {w}%")
        if a is not None: suffix.append(f"{a} acciones")
        if suffix:
            subject += " | " + " | ".join(suffix)

    msg = EmailMessage()
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["From"] = cfg.get("sender_alias", "Medallio Ambassador")
    msg.set_content("Medallio Ambassador requiere un cliente compatible con HTML.")
    msg.add_alternative(html_body, subtype="html")

    for p in attachments:
        ctype, encoding = mimetypes.guess_type(p.name)
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)

    return msg

def send_message(root: Path, cfg: dict, msg: EmailMessage):
    creds = gmail_credentials(root, cfg)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()

def outbox_dir(root: Path) -> Path:
    d = root / "artifacts" / "medallio_ambassador" / "outbox"
    d.mkdir(parents=True, exist_ok=True)
    return d

def save_outbox(root: Path, msg: EmailMessage):
    p = outbox_dir(root) / f"{datetime.now():%Y%m%d_%H%M%S}.eml"
    p.write_bytes(msg.as_bytes())
    logging.warning("Correo guardado en outbox: %s", p)
    return p

def retry_outbox(root: Path, cfg: dict):
    files = sorted(outbox_dir(root).glob("*.eml"))
    if not files:
        return
    from email import policy
    from email.parser import BytesParser
    for p in files[:3]:
        try:
            msg = BytesParser(policy=policy.default).parsebytes(p.read_bytes())
            send_message(root, cfg, msg)
            p.unlink()
            logging.info("Outbox enviado: %s", p.name)
        except Exception:
            logging.exception("No se pudo reenviar outbox %s", p.name)
            break

def append_history(root: Path, slot: str, results: list[dict], sent: bool, attachments: list[Path]):
    p = root / "artifacts" / "medallio_ambassador" / "run_history.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists()
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp","slot","notebooks_ok","notebooks_error","email_sent","attachments","attachment_mb"])
        ok = sum(r["status"] == "OK" for r in results)
        err = sum(r["status"] == "ERROR" for r in results)
        total_size = sum(x.stat().st_size for x in attachments if x.exists())/1024/1024
        w.writerow([datetime.now().isoformat(timespec="seconds"),slot,ok,err,int(sent),len(attachments),round(total_size,2)])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["morning","midday","evening"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = find_repo_root()
    cfg = load_config(root)
    setup_logging(root)

    lock_path = root / "artifacts" / "medallio_ambassador" / ".lock"
    with FileLock(lock_path):
        logging.info("Medallio Ambassador start | slot=%s", args.slot)
        run_started_epoch = time.time()

        if not args.dry_run:
            try:
                retry_outbox(root, cfg)
            except Exception:
                logging.exception("Retry outbox falló")

        notebook_list = list(cfg["notebooks"]["every_run"])
        if args.slot == "evening":
            notebook_list += list(cfg["notebooks"].get("evening_only", []))

        results = []
        for rel in notebook_list:
            timeout_map = cfg.get("notebook_timeouts_seconds", {})
            notebook_timeout = int(
                timeout_map.get(rel, cfg.get("notebook_timeout_seconds", 1200))
            )
            logging.info("Timeout asignado a %s: %ss", rel, notebook_timeout)
            r = execute_notebook(
                root,
                rel,
                notebook_timeout,
                cfg.get("kernel_name"),
            )
            results.append(r)
            if r["status"] == "ERROR" and not cfg.get("continue_on_notebook_error", True):
                break

        # Sólo usar evidencia creada en ESTA corrida.
        freshness_cutoff = run_started_epoch - 5
        board = latest_board_summary(root, freshness_cutoff)
        decisions = latest_decisions(root, freshness_cutoff)
        attachments = select_attachments(root, cfg, freshness_cutoff)
        html = build_email_html(args.slot, results, board, decisions)
        msg = make_message(cfg, args.slot, html, attachments, board)

        sent = False
        if args.dry_run:
            preview = root / "artifacts" / "medallio_ambassador" / f"preview_{args.slot}.html"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_text(html, encoding="utf-8")
            logging.info("DRY RUN. Preview: %s", preview)
        else:
            try:
                response = send_message(root, cfg, msg)
                sent = True
                logging.info("Gmail enviado. message_id=%s", response.get("id"))
            except Exception:
                logging.exception("Fallo de Gmail; se guarda en outbox.")
                save_outbox(root, msg)

        append_history(root, args.slot, results, sent, attachments)
        logging.info("Medallio Ambassador end")

if __name__ == "__main__":
    main()
