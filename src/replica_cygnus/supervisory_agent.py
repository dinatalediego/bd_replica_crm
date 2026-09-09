from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from .connections import connect_postgres
from .platform_control import (
    ensure_platform_control,
    platform_status_rows,
    refresh_platform_controls,
)


@dataclass(frozen=True)
class SupervisoryHealth:
    status: str
    score: float
    summary: str
    controls: list[dict[str, Any]]


def _status_rank(status: str) -> int:
    return {
        "BLOCKED": 4,
        "FAIL": 4,
        "IN_PROGRESS": 2,
        "WARN": 2,
        "NOT_STARTED": 1,
        "UNKNOWN": 1,
        "DONE": 0,
        "OK": 0,
    }.get((status or "UNKNOWN").upper(), 1)


def summarize_platform(rows: list[tuple]) -> SupervisoryHealth:
    controls: list[dict[str, Any]] = []
    scores: list[float] = []
    worst_rank = 0
    blocked: list[str] = []
    warning: list[str] = []

    for row in rows:
        app, layer, criticality, score, health, done, total, *rest = row
        raw_score = float(score or 0.0)
        pct_score = raw_score * 100.0 if raw_score <= 1.0 else raw_score
        scores.append(max(0.0, min(100.0, pct_score)))
        health_text = str(health or "UNKNOWN").upper()
        rank = _status_rank(health_text)
        worst_rank = max(worst_rank, rank)
        if rank >= 4:
            blocked.append(str(app))
        elif rank >= 2:
            warning.append(str(app))
        controls.append(
            {
                "application": app,
                "layer": layer,
                "criticality": criticality,
                "score": round(pct_score, 2),
                "health": health_text,
                "done": int(done or 0),
                "total": int(total or 0),
                "details": list(rest),
            }
        )

    overall_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    if not rows:
        status = "UNKNOWN"
    elif worst_rank >= 4:
        status = "FAIL"
    elif worst_rank >= 2:
        status = "WARN"
    else:
        status = "OK"

    if status == "OK":
        summary = f"Plataforma estable. {len(rows)} componentes revisados."
    elif status == "WARN":
        names = ", ".join(warning[:3]) or "controles pendientes"
        summary = f"Plataforma operativa con observaciones: {names}."
    elif status == "FAIL":
        names = ", ".join(blocked[:3]) or "controles bloqueados"
        summary = f"Se requiere revisión: {names}."
    else:
        summary = "No hay evidencia suficiente para clasificar la plataforma."

    return SupervisoryHealth(status, overall_score, summary, controls)


class MonitorClient:
    def __init__(self, base_url: str, token: str, *, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"accept": "application/json", "x-agent-token": self.token}
        if data is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Monitor API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Monitor API unavailable: {exc.reason}") from exc

    def heartbeat(self, health: SupervisoryHealth, *, notify: bool = False) -> dict[str, Any]:
        return self._request(
            "POST",
            "heartbeat",
            body={
                "agent_id": os.getenv("CYGNUS_AGENT_ID", "cygnus-local-dw"),
                "health_status": health.status,
                "health_score": health.score,
                "summary": health.summary,
                "payload": {"controls": health.controls},
                "notify": notify,
            },
        )

    def commands(self) -> list[dict[str, Any]]:
        agent_id = urllib.parse.quote(os.getenv("CYGNUS_AGENT_ID", "cygnus-local-dw"))
        return self._request("GET", f"commands?agent_id={agent_id}").get("commands", [])

    def report(self, health: SupervisoryHealth) -> dict[str, Any]:
        headline = health.summary
        critical = [c for c in health.controls if _status_rank(c["health"]) >= 2]
        return self._request(
            "POST",
            "report",
            body={
                "agent_id": os.getenv("CYGNUS_AGENT_ID", "cygnus-local-dw"),
                "report_kind": "EXECUTIVE",
                "title": "Reporte Ejecutivo Cygnus",
                "summary": headline,
                "payload": {
                    "health_status": health.status,
                    "health_score": health.score,
                    "attention_required": critical[:8],
                    "controls": health.controls,
                },
            },
        )

    def complete_command(self, command_id: str, *, ok: bool, result: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "command-result",
            body={"id": command_id, "ok": ok, "result": result},
        )


def collect_platform_health(settings) -> SupervisoryHealth:
    with connect_postgres(settings) as conn:
        ensure_platform_control(conn, settings.project_root)
        refresh_platform_controls(conn, settings.project_root)
        rows = platform_status_rows(conn)
    return summarize_platform(rows)


def run_once(settings, *, notify: bool = False) -> dict[str, Any]:
    base_url = os.getenv("CYGNUS_MONITOR_URL", "").strip()
    token = os.getenv("CYGNUS_AGENT_TOKEN", "").strip()
    if not base_url:
        raise RuntimeError("CYGNUS_MONITOR_URL is required")
    if not token:
        raise RuntimeError("CYGNUS_AGENT_TOKEN is required")

    health = collect_platform_health(settings)
    client = MonitorClient(base_url, token)
    heartbeat = client.heartbeat(health, notify=notify)
    command_results: list[dict[str, Any]] = []

    for command in client.commands():
        command_id = str(command["id"])
        command_type = str(command.get("command_type", ""))
        try:
            if command_type == "GENERATE_REPORT":
                report_result = client.report(health)
                result = {"generated": True, "remote": report_result}
                client.complete_command(command_id, ok=True, result=result)
            elif command_type == "RUN_HEALTH_CHECK":
                result = {"health": asdict(health)}
                client.complete_command(command_id, ok=True, result=result)
            elif command_type == "SEND_REPORT":
                # Approval has been captured by the control plane. Distribution to
                # management is intentionally a separate channel-specific adapter.
                # Until a recipient/channel contract is configured, keep this auditable
                # rather than pretending that a report was delivered.
                result = {
                    "approved": True,
                    "delivery_status": "READY_FOR_DISTRIBUTION",
                    "note": "Management distribution channel not configured yet",
                }
                client.complete_command(command_id, ok=True, result=result)
            else:
                client.complete_command(
                    command_id,
                    ok=False,
                    result={"error": f"Unsupported command_type: {command_type}"},
                )
            command_results.append({"id": command_id, "type": command_type, "ok": True})
        except Exception as exc:  # command failures should not lose the heartbeat
            client.complete_command(command_id, ok=False, result={"error": str(exc)})
            command_results.append({"id": command_id, "type": command_type, "ok": False, "error": str(exc)})

    return {
        "health": asdict(health),
        "heartbeat": heartbeat,
        "commands": command_results,
    }
