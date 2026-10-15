from pathlib import Path
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def find_repo_root():
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / ".env.example").exists():
            return candidate
    return p

root = find_repo_root()
config_path = root / "config" / "medallio_ambassador.json"
if not config_path.exists():
    raise SystemExit(
        f"No existe {config_path}. Copia medallio_ambassador.example.json como medallio_ambassador.json."
    )

cfg = json.loads(config_path.read_text(encoding="utf-8"))
credentials_path = root / cfg["gmail"]["credentials_file"]
token_path = root / cfg["gmail"]["token_file"]
token_path.parent.mkdir(parents=True, exist_ok=True)

if not credentials_path.exists():
    raise SystemExit(
        f"Falta {credentials_path}. Descarga un OAuth Client ID de tipo Desktop App desde Google Cloud."
    )

flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
creds = flow.run_local_server(port=0)
token_path.write_text(creds.to_json(), encoding="utf-8")

print("OAuth Gmail configurado.")
print("Token:", token_path)
