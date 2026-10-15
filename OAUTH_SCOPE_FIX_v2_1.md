# OAuth v2.1 — ScopeChanged fix

Tu captura muestra dos problemas relacionados pero distintos.

## 1. `Authorized user info was not in expected format`

Eso ocurre cuando `Credentials.from_authorized_user_file()` recibe un archivo que no
es un token de usuario válido. Los dos archivos deben ser diferentes:

### Cliente OAuth descargado de Google Cloud

```text
.secrets\google_workspace_credentials.json
```

Debe verse así:

```json
{
  "installed": {
    "client_id": "...",
    "project_id": "...",
    "auth_uri": "...",
    "token_uri": "...",
    "client_secret": "...",
    "redirect_uris": [...]
  }
}
```

### Token generado por Ambassador

```text
.secrets\google_workspace_token.json
```

Lo genera `google_workspace_oauth_v2.py` después de que autorizas en el navegador.
No copies manualmente el JSON de credenciales dentro del token.

## 2. `Scope has changed from ... to ...`

La primera versión usaba:

```python
include_granted_scopes="true"
```

Google podía devolver scopes históricos de la misma autorización, por ejemplo
`drive.readonly`, aunque Ambassador estaba solicitando `drive.file`.

`requests-oauthlib` lo interpreta como un cambio de scope y lanza el ValueError.

### Fix v2.1

- ya no usa `include_granted_scopes`;
- solicita exactamente los scopes necesarios;
- Google Chat sólo se solicita si `chat.enabled=true` y existe `space_name`;
- fuerza `prompt="consent"` y `access_type="offline"` para obtener refresh token;
- valida que `credentials_file` y `token_file` no estén confundidos;
- el runner exige sólo los scopes de las funciones actualmente habilitadas.

## Instalación mínima

Reemplaza:

```text
scripts\google_workspace_oauth_v2.py
scripts\validate_google_workspace_v2.py
scripts\medallio_ambassador_v2.py
```

Mantén por ahora:

```json
"chat": {
  "enabled": false,
  "space_name": ""
}
```

## Reautorizar limpio

Cierra cualquier proceso Ambassador y ejecuta:

```powershell
python .\scripts\google_workspace_oauth_v2.py
```

El script respalda automáticamente el token actual.

Después:

```powershell
python .\scripts\validate_google_workspace_v2.py
```

Y finalmente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Si Google sigue devolviendo scopes históricos

En tu Cuenta de Google, revoca una sola vez el acceso de la app OAuth de este proyecto
y vuelve a ejecutar `google_workspace_oauth_v2.py`.

No es necesario borrar el proyecto de Google Cloud ni volver a habilitar APIs.
