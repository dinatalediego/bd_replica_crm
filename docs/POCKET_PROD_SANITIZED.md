# Medallio Pocket PROD — Supabase sanitizado

## Objetivo

Publicar al APK únicamente información agregada y validada. El proyecto Supabase Pocket NO es una réplica de `medallio_dw`.

Arquitectura:

```text
Redshift / CRM
    ↓
medallio_dw local
    ↓
analytics.v_stock_movimiento_mensual_export
    ↓
analytics.v_pocket_commercial_project_month
    ↓  HMAC project_ref + allowlist + privacy gate
Supabase Pocket PROD
    ↓  Auth + RLS + SELECT-only
Android APK
```

## Agregado comercial real

`analytics.v_pocket_commercial_project_month` tiene grano `proyecto × mes` y se alimenta de evidencia observada del ledger comercial.

Incluye únicamente:

- proyecto;
- periodo;
- stock inicial/final;
- separaciones brutas;
- caídas;
- separaciones netas;
- ventas/minutas;
- absorción bruta/neta;
- absorción neta 6m;
- stock actual y cobertura;
- flags de calidad/frescura.

No incluye:

- cliente;
- lead;
- DNI/documento;
- teléfono/celular;
- correo;
- dirección;
- asesor;
- proforma;
- unidad;
- notas/comentarios/conversaciones;
- grabaciones;
- texto libre CRM.

`analytics.v_pocket_commercial_privacy_audit` debe devolver **0 filas**.

## Instalación local

```powershell
.\.venv\Scripts\python.exe .\scripts\install_pocket_commercial.py
```

La instalación es idempotente y también valida el privacy contract.

## Dry run del export

Configura únicamente el HMAC local:

```powershell
$env:POCKET_PROJECT_HMAC_KEY="<32+ bytes aleatorios>"
.\.venv\Scripts\python.exe .\scripts\sync_pocket_prod.py --dry-run
```

No se conecta al Pocket Supabase en `--dry-run`.

## Supabase Pocket PROD

Aplicar en el proyecto Supabase aislado:

1. `supabase/pocket_prod/001_schema.sql`
2. `supabase/pocket_prod/002_privacy_audit.sql`
3. crear usuario(s) en Supabase Auth;
4. insertar únicamente los usuarios autorizados en `public.pocket_access`.

El esquema usa:

- RLS en todas las tablas `pocket_*`;
- `anon` sin privilegios;
- `authenticated` con `SELECT` solamente;
- policy adicional que exige `pocket_access.active = true`;
- `private.pocket_sync_runs` fuera del Data API.

## Sincronización real

Variables solo para la PC/servidor:

```powershell
$env:POCKET_SUPABASE_DB_URL="postgresql://..."
$env:POCKET_PROJECT_HMAC_KEY="<32+ bytes aleatorios>"
.\.venv\Scripts\python.exe .\scripts\sync_pocket_prod.py
```

El proceso:

1. lee `medallio_dw` mediante la configuración local existente;
2. valida la allowlist exacta de columnas;
3. rechaza columnas inesperadas/PII;
4. convierte `codigo_proyecto` en un `project_ref` HMAC estable;
5. reemplaza atómicamente el snapshot `pocket_project_month` y `pocket_project_summary`;
6. vuelve a ejecutar el privacy audit del destino.

## Automatización horaria

`scripts/dw_refresh.py` detecta las dos variables `POCKET_*`.

Si están configuradas, añade al final del refresh:

```text
09a_pocket_commercial_contract
09b_pocket_prod_sync
```

Si no están configuradas, no cambia el comportamiento del refresh maestro.

## Android

El APK recibe únicamente:

```text
SUPABASE_URL
sb_publishable_...
```

Nunca incluir en Android:

```text
POCKET_SUPABASE_DB_URL
POCKET_PROJECT_HMAC_KEY
service_role
sb_secret_...
credenciales Redshift/PostgreSQL
```

## Semántica de negocio

`ventas_minutas_mes` proviene del ledger observado y está etiquetado en la fuente como `VENTA_EFECTIVA / MINUTA_CANONICA`.

La absorción mostrada por Pocket es `absorcion_neta_mes = (separaciones efectivas - caídas) / stock inicial observado`.

No se infieren minutas a partir de cambios de stock público.
