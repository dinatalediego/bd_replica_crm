# Medallio Ambassador v2 — Enterprise Intelligence Operations

## Qué hace

Ambassador v2 convierte los notebooks locales de Medallio en una operación ejecutiva:

```text
medallio_dw local
      │
      ├─ CEO 5-Minute Briefing
      └─ AI Control Tower Lite
              │
              ▼
       Executive Digest
              │
      ┌───────┼────────┬────────┬────────┬────────┐
      ▼       ▼        ▼        ▼        ▼        ▼
    Gmail    Drive    Sheets   Slides    Docs   Calendar/Chat
    3/día    Vault    Memory   Board     Memo    Escalation
```

## Política por canal

**Gmail — 3 veces al día**
- headline;
- cambios desde el briefing anterior;
- máximo 3 decisiones;
- máximo 3 attachments;
- links a Drive, Sheets, Slides y Docs.

**Drive — cada corrida**
- `Medallio Intelligence Vault / YYYY-MM-DD / Morning|Midday|Evening`
- almacena evidencia fresca de esa corrida.

**Sheets — memoria estructurada**
- `RUNS`
- `DECISIONS`
- `ARTIFACTS`
- `OUTCOMES`

**Slides — Morning y Evening**
- deck diario;
- un slide ejecutivo por slot.

**Docs — memo semanal**
- acumula briefings Evening en un documento semanal.

**Calendar — sólo CRITICAL**
- crea un `Decision Review` de 20 minutos;
- deduplicado por fingerprint.

**Google Chat — HIGH / CRITICAL**
- desactivado hasta configurar `space_name`;
- pensado para alertas urgentes, no reportes.

## Noise control

El email no repite todo. Compara contra la corrida anterior.

Umbrales por defecto:
- WAPE: 2 pp;
- cobertura: 5 pp;
- acciones abiertas: 2;
- alertas: 1;
- Trust Score: 5 pp.

## Seguridad

- OAuth Desktop, no contraseña Gmail.
- Scope `drive.file`, no acceso general a Drive.
- `.secrets/` fuera de Git.
- artifacts de correo = corrida actual.
- Calendar y Chat con deduplicación.
- Secret Manager, Pub/Sub y BigQuery incluidos como adaptadores opcionales.
- Mientras PostgreSQL siga local, Windows Task Scheduler sigue siendo el scheduler principal.

## Instalación

Descomprime en:

```text
C:\Projects\bd_replica_crm
```

Luego:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ambassador-v2.txt
Copy-Item .\config\medallio_ambassador_v2.example.json .\config\medallio_ambassador_v2.json
```

Edita `recipient`.

## Reautorizar OAuth

Tu token anterior probablemente tiene sólo Gmail.

Coloca tu OAuth Desktop JSON en:

```text
.secrets\google_workspace_credentials.json
```

Luego:

```powershell
python .\scripts\google_workspace_oauth_v2.py
```

## Validación

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Scheduler

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_medallio_ambassador_v2.ps1
```

Defaults:
- 08:00
- 13:00
- 18:30

## Cloud opcional

Secret Manager / Pub/Sub / BigQuery quedan desactivados inicialmente para mantener costo y complejidad bajos.
Actívalos después de estabilizar Workspace.
