# Ambassador v2.3 — Fault Isolation / Degraded Mode

## Qué pasó en tu corrida

La ejecución llegó correctamente hasta las integraciones Google y falló en Google Docs:

```text
403 SERVICE_DISABLED
service: docs.googleapis.com
consumer: projects/568724071159
```

Eso significa que, para el proyecto OAuth que está usando Ambassador, Google Docs API:
- todavía estaba deshabilitada, o
- acababa de habilitarse y aún no había propagado, o
- fue habilitada en otro proyecto distinto.

El validator v2.2 sí hizo su trabajo: comprobó OAuth y scopes.
Crear un cliente API no confirma que el servicio esté habilitado en Google Cloud.

## Fix operativo inmediato

Comprueba que **Google Docs API** esté habilitada en el proyecto cuyo número es:

```text
568724071159
```

Si acabas de habilitarla, espera unos minutos y prueba nuevamente.

También puedes verificar qué proyecto pertenece al OAuth Desktop JSON:

```powershell
(Get-Content .\.secrets\google_workspace_credentials.json -Raw | ConvertFrom-Json).installed.project_id
```

## Por qué v2.3 es más corporativo

Una API secundaria no debe tumbar todo el briefing.

v2.3 introduce **fault isolation por canal**:

- Drive falla → Sheets/Slides/Gmail continúan.
- Sheets falla → Drive/Gmail continúan.
- Docs falla → Gmail continúa.
- Calendar/Chat fallan → no interrumpen el briefing.
- Gmail falla → guarda el `.eml` en `artifacts\medallio_ambassador\outbox`.

Además:

### Docs sólo corre en Evening
Morning y Midday ya no tocan Docs.
El memo semanal es una función de cierre, no una dependencia del briefing matutino.

## Instalación

Reemplaza:

```text
scripts\medallio_ambassador_v2.py
```

Luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```

Si Docs siguiera temporalmente deshabilitado, Morning debería finalizar igualmente
porque v2.3 no invoca Docs en ese slot.

## Modo degradado

En logs verás:

```text
CHANNEL OK | Drive
CHANNEL OK | Sheets
CHANNEL OK | Slides
CHANNEL OK | Docs
...
```

o:

```text
CHANNEL DEGRADED | Docs | HttpError...
```

El correo incluirá en cambios:

```text
Canales degradados: docs
```

sin perder el resto del briefing.
