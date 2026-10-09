from __future__ import annotations

from pathlib import Path
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


BASE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/calendar.events",
]

CHAT_SCOPE = "https://www.googleapis.com/auth/chat.messages.create"


def find_repo_root():
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / ".env.example").exists():
            return candidate
    return p


def required_scopes(cfg):
    scopes = list(BASE_SCOPES)
    chat = cfg.get("google", {}).get("chat", {})
    if chat.get("enabled") and chat.get("space_name"):
        scopes.append(CHAT_SCOPE)
    return scopes


def validate_token_shape(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))

    if "installed" in data or "web" in data:
        raise SystemExit(
            "El archivo configurado como token contiene credenciales de cliente OAuth, "
            "no un token autorizado.\n"
            f"Ruta: {path}\n"
            "Ejecuta google_workspace_oauth_v2.py para generar el token correcto."
        )

    required = {"client_id", "client_secret", "refresh_token", "token_uri"}
    missing = sorted(required - set(data.keys()))
    if missing:
        raise SystemExit(
            "El token OAuth no tiene el formato esperado.\n"
            f"Ruta: {path}\n"
            f"Faltan: {missing}\n"
            "Vuelve a generarlo con google_workspace_oauth_v2.py."
        )


def main():
    root = find_repo_root()
    cfg_path = root / "config" / "medallio_ambassador_v2.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    token = root / cfg["paths"]["token_file"]
    if not token.exists():
        raise SystemExit(
            f"Falta {token}. Ejecuta google_workspace_oauth_v2.py."
        )

    validate_token_shape(token)

    required = required_scopes(cfg)
    creds = Credentials.from_authorized_user_file(str(token), required)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")

    granted = set(creds.scopes or [])
    missing = sorted(set(required) - granted)

    print("Token OAuth:", token)
    print("Estado:", "VALID" if creds.valid else "INVALID")
    print("\nScopes requeridos:")
    for scope in required:
        print(" [OK] " if scope in granted else " [MISSING] ", scope)

    if missing:
        raise SystemExit(
            "\nFaltan scopes requeridos:\n - " + "\n - ".join(missing)
            + "\nReautoriza con google_workspace_oauth_v2.py."
        )

    # IMPORTANTE:
    # No hacemos users.getProfile(), calendarList.list() ni otros endpoints de lectura.
    # Ambassador usa scopes mínimos deliberadamente:
    #   gmail.send        -> enviar, no leer perfil/mailbox
    #   drive.file        -> archivos creados/usados por la app
    #   calendar.events   -> eventos, no calendarList
    #
    # Un "validator" que llama endpoints de lectura puede producir falsos 403 aunque
    # el token sea perfectamente válido para las operaciones reales de Ambassador.

    services = {
        "Gmail": build("gmail", "v1", credentials=creds, cache_discovery=False),
        "Drive": build("drive", "v3", credentials=creds, cache_discovery=False),
        "Sheets": build("sheets", "v4", credentials=creds, cache_discovery=False),
        "Slides": build("slides", "v1", credentials=creds, cache_discovery=False),
        "Docs": build("docs", "v1", credentials=creds, cache_discovery=False),
        "Calendar": build("calendar", "v3", credentials=creds, cache_discovery=False),
    }

    if cfg.get("google", {}).get("chat", {}).get("enabled"):
        services["Chat"] = build(
            "chat", "v1", credentials=creds, cache_discovery=False
        )

    print("\nClientes API construidos:")
    for name in services:
        print(" [OK]", name)

    print("\nWorkspace OAuth v2.2: OK")
    print(
        "Nota: esta validación es scope-aware y no pide permisos de lectura "
        "que Ambassador no necesita."
    )
    print("\nSiguiente prueba real, sin enviar email:")
    print(r"python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run")
    print("\nLuego prueba integrada real:")
    print(r"python .\scripts\medallio_ambassador_v2.py --slot morning")


if __name__ == "__main__":
    main()
