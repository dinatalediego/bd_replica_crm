# Ambassador v2.2 — Scope-aware validator

## Qué significa tu 403

El token no está necesariamente mal.

El validator v2.1 hacía:

```python
gmail.users().getProfile(userId="me").execute()
```

pero Ambassador autoriza Gmail con:

```text
https://www.googleapis.com/auth/gmail.send
```

Ese scope está diseñado para **enviar correo**, no para leer el perfil/mailbox.

Por tanto:

```text
403 insufficient authentication scopes
```

era un **falso negativo del validator**.

Lo mismo podía pasar después con validaciones demasiado amplias de Drive o Calendar:
- `drive.file` es intencionalmente limitado;
- `calendar.events` no equivale a acceso completo al Calendar.

## Qué cambia

v2.2 valida:
1. formato correcto del token;
2. refresh token;
3. token válido;
4. scopes exactos requeridos;
5. creación de clientes Gmail/Drive/Sheets/Slides/Docs/Calendar;
6. Chat sólo si está habilitado.

No llama endpoints de lectura que exijan scopes adicionales.

## Por qué esto es mejor

Mantiene el principio de menor privilegio:

- Gmail: sólo enviar.
- Drive: sólo archivos que la app crea/usa.
- Calendar: eventos.
- Chat: sólo si realmente se activa.

No ampliamos permisos sólo para satisfacer un script de diagnóstico.

## Instalación

Reemplaza únicamente:

```text
scripts\validate_google_workspace_v2.py
```

Luego:

```powershell
python .\scripts\validate_google_workspace_v2.py
```

Si sale `Workspace OAuth v2.2: OK`, sigue con:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

y después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```
