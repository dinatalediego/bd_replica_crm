# Medallio Ambassador

Sistema local para ejecutar los notebooks de Medallio automáticamente, recoger sus artefactos de mayor valor y enviar un briefing por Gmail.

## Diseño

- **3 ejecuciones al día** mediante Windows Task Scheduler.
- **Morning / Midday:** ejecuta los notebooks más ejecutivos.
- **Evening:** añade los notebooks profundos.
- **Read-only respecto a Medallio:** sólo ejecuta los notebooks existentes.
- **Gmail API:** OAuth local; no guarda contraseña de Gmail.
- **Budget de adjuntos:** 18 MiB por defecto para mantenerse debajo del límite de Gmail después del overhead MIME/base64.
- **Artifact ranking:** prioriza Decision Queue, Board Summary y PNG ejecutivos; evita adjuntar notebooks pesados.
- **Outbox:** si Gmail falla, guarda el mensaje y vuelve a intentarlo en la siguiente corrida.
- **Logs + lock:** evita ejecuciones simultáneas y deja trazabilidad.

## Estructura esperada

```text
C:\Projects\bd_replica_crm\
├─ .venv\
├─ notebooks\
│  ├─ Medallio_CEO_5_Minute_AI_Briefing.ipynb
│  ├─ Medallio_Enterprise_AI_Control_Tower_v2.ipynb
│  ├─ Medallio_Enterprise_AI_Analytics_Operating_System.ipynb
│  └─ Medallio_AI_Analytics_Factory.ipynb
├─ scripts\
│  └─ medallio_ambassador\
│     ├─ run_ambassador.py
│     └─ gmail_oauth_setup.py
├─ config\
│  └─ medallio_ambassador.json
├─ .secrets\
│  ├─ gmail_credentials.json
│  └─ gmail_token.json
└─ artifacts\
```

## 1. Instalar dependencias

Desde PowerShell:

```powershell
cd C:\Projects\bd_replica_crm
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ambassador.txt
```

## 2. Configurar destinatario

Copia:

```text
config\medallio_ambassador.example.json
```

como:

```text
config\medallio_ambassador.json
```

y cambia:

```json
"recipient": "TU_CORREO@gmail.com"
```

## 3. Crear OAuth de Gmail una sola vez

En Google Cloud:
1. Crea un proyecto.
2. Habilita **Gmail API**.
3. Configura OAuth consent screen para uso personal.
4. Crea **OAuth client ID → Desktop app**.
5. Descarga el JSON y guárdalo como:

```text
C:\Projects\bd_replica_crm\.secrets\gmail_credentials.json
```

Luego:

```powershell
python scripts\medallio_ambassador\gmail_oauth_setup.py
```

Se abrirá el navegador para autorizar `gmail.send` y se creará `.secrets\gmail_token.json`.

> Nunca subas `.secrets/` a Git.

## 4. Prueba manual

Sin enviar correo:

```powershell
python scripts\medallio_ambassador\run_ambassador.py --slot morning --dry-run
```

Ejecutar y enviar:

```powershell
python scripts\medallio_ambassador\run_ambassador.py --slot morning
```

## 5. Programar 3 veces al día

Ejecuta PowerShell **como usuario normal**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\medallio_ambassador\install_scheduled_task.ps1
```

Defaults:
- 08:00 — Morning
- 13:00 — Midday
- 18:30 — Evening

Puedes cambiarlos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\medallio_ambassador\install_scheduled_task.ps1 `
  -Morning "07:45" -Midday "13:15" -Evening "18:45"
```

## Política de calidad/peso

### Cada corrida
1. `Medallio_CEO_5_Minute_AI_Briefing.ipynb`
2. `Medallio_Enterprise_AI_Control_Tower_v2.ipynb`

### Sólo Evening
3. `Medallio_Enterprise_AI_Analytics_Operating_System.ipynb`
4. `Medallio_AI_Analytics_Factory.ipynb`

Así no gastas tiempo/CPU ejecutando cuatro notebooks pesados tres veces al día.

## Prioridad de adjuntos

1. `board_summary.json`
2. `ceo_decision_queue.csv`
3. `ceo_control_tower_summary.csv`
4. gráficos que contienen `ceo`, `value`, `forecast`, `decision`, `portfolio`, `confidence`
5. otros PNG
6. CSV / JSON restantes

No adjunta `.ipynb` ejecutados por defecto.

## Salida

```text
artifacts\medallio_ambassador\
├─ logs\
├─ outbox\
└─ run_history.csv
```

Y reutiliza los artefactos producidos por los notebooks en:
- `artifacts\medallio_ceo_briefing`
- `artifacts\medallio_enterprise`
- `artifacts\medallio_ai_factory`
