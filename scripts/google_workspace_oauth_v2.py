from __future__ import annotations

from pathlib import Path
import json
import shutil
from datetime import datetime

from google_auth_oauthlib.flow import InstalledAppFlow


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


def required_scopes(cfg: dict) -> list[str]:
    scopes = list(BASE_SCOPES)
    chat = cfg.get("google", {}).get("chat", {})
    if chat.get("enabled") and chat.get("space_name"):
        scopes.append(CHAT_SCOPE)
    return scopes


def validate_client_credentials(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "installed" not in data:
        raise SystemExit(
            "El archivo de credenciales no parece ser un OAuth Client ID de tipo Desktop App.\n"
            f"Ruta: {path}\n"
            "Debe contener una clave raíz 'installed'. Descarga el JSON de "
            "Google Cloud > APIs & Services > Credentials > OAuth 2.0 Client IDs > Desktop app."
        )
    required = {"client_id", "client_secret", "auth_uri", "token_uri", "redirect_uris"}
    missing = sorted(required - set(data["installed"].keys()))
    if missing:
        raise SystemExit(
            f"El OAuth client JSON está incompleto. Faltan: {missing}"
        )


def main():
    root = find_repo_root()
    cfg_path = root / "config" / "medallio_ambassador_v2.json"
    if not cfg_path.exists():
        raise SystemExit(
            f"Falta {cfg_path}. Copia medallio_ambassador_v2.example.json."
        )

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    credentials_path = root / cfg["paths"]["credentials_file"]
    token_path = root / cfg["paths"]["token_file"]
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if not credentials_path.exists():
        raise SystemExit(
            f"Falta {credentials_path}.\n"
            "Guarda allí el OAuth Client ID descargado como Desktop App."
        )

    validate_client_credentials(credentials_path)

    scopes = required_scopes(cfg)

    if token_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = token_path.with_name(f"{token_path.stem}_{stamp}.bak.json")
        shutil.move(str(token_path), str(backup))
        print("Token anterior respaldado en:", backup)

    print("\nScopes solicitados EXACTAMENTE:")
    for scope in scopes:
        print(" -", scope)

    if CHAT_SCOPE not in scopes:
        print(
            "\nGoogle Chat queda fuera de esta autorización porque chat.enabled=false "
            "o no tiene space_name. Puedes habilitarlo más adelante y reautorizar."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path),
        scopes,
    )

    # No usamos include_granted_scopes=True.
    # Eso puede mezclar scopes históricos de autorizaciones anteriores
    # (por ejemplo drive.readonly) y provocar ScopeChangedWarning/ValueError.
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    token_path.write_text(creds.to_json(), encoding="utf-8")

    print("\nOAuth Ambassador v2.1 configurado.")
    print("Token:", token_path)
    print("Scopes concedidos:")
    for scope in sorted(creds.scopes or []):
        print(" -", scope)

    print("\nSiguiente paso:")
    print(r"python .\scripts\validate_google_workspace_v2.py")


if __name__ == "__main__":
    main()
