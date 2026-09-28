# Portal Conversion Attribution — Medallio

## Objetivo

Construir dentro de `bd_replica_crm` un mart reproducible para responder, por `medio_captacion`:

> De todos los leads recibidos, ¿cuántas personas terminaron en una `Separacion` que continúa `Activo`?

El sistema reemplaza el cruce manual de tres Excel y deja la evidencia en PostgreSQL antes de generar el XLSX ejecutivo.

## Fuentes

### ORIGEN — fuente prioritaria

`raw_cygnus.clientes_proyectos`

- `fecha_creacion >= 2026-01-01` (configurable con `--start-year`);
- se usan todos los `medio_captacion`, no solo Urbania;
- conserva proyecto, UTM, asignación, nivel de interés y documento.

Equivale a la base antes llamada `leads_origen_urbania_2026`.

### MEDIO_ACTUAL

`raw_cygnus.interacciones`

- `nombre = 'portal inmobiliario'`;
- `fecha_creacion >= 2026-01-01`;
- se usan todos los `medio_captacion`.

Equivale a `leads_medio_actual_urbania_2026`.

### Compradores / convertidos

`raw_cygnus.procesos`

- `nombre = 'Separacion'`;
- `estado = 'Activo'`;
- `fecha_inicio >= 2026-01-01`.

La identidad y el `medio_captacion` del cliente se enriquecen desde `staging.clientes_calidad`, que deriva de `raw_cygnus.clientes`.

## Reglas de negocio

### Prioridad ORIGEN > MEDIO_ACTUAL

Cuando el mismo lead existe en ambas fuentes, la fila de `MEDIO_ACTUAL` se conserva para auditoría, pero queda con:

- `duplicado_en_origen = true`;
- `incluir_en_kpi = false`;
- `lead_origen_uid` apuntando al lead prioritario.

La detección usa identidad fuerte y proyecto: DNI, documento fuente, email+celular, email+nombre o celular+nombre. No se deduplica por nombre solo.

### Deduplicación de la conversión

Una persona convertida cuenta **una sola vez**.

Prioridad de llave:

1. DNI exacto de 8 dígitos;
2. email + celular;
3. email;
4. celular;
5. documento fuente;
6. proceso como fallback técnico.

Si `raw_cygnus.procesos` tiene varias filas para el mismo DNI por unidades/proformas, se conserva la primera `fecha_inicio` activa y se registra `filas_proceso_deduplicadas`.

### Cuatro controles de match

Cada lead pasa por:

1. **DNI**: 100 puntos únicamente si ambos valores son exactamente los mismos 8 dígitos. `auto-*` jamás es DNI.
2. **Nombre**: tildes, mayúsculas, puntuación y orden de tokens normalizados; similitud fuzzy 0–100.
3. **Celular**: dígitos y `+51` normalizados; exacto o fuzzy controlado.
4. **Email**: minúsculas, espacios removidos, fuzzy controlado y penalización si cambia el dominio.

Estados:

- `CONFIRMADO`: DNI exacto o evidencia de contacto casi exacta corroborada;
- `PROBABLE`: dos evidencias consistentes; sí entra al KPI automático;
- `REVISAR`: evidencia parcial; no entra al KPI;
- `NO MATCH`: evidencia insuficiente.

El nombre por sí solo nunca convierte automáticamente.

### Gate temporal

`fecha_separacion >= fecha_creacion`.

Una separación anterior al lead no puede atribuirse.

### Atribución única

Aunque una persona tenga varios leads, `conversion_atribuida = true` solo puede aparecer una vez por `conversion_key`.

Desempate:

1. `CONFIRMADO > PROBABLE`;
2. mayor `score_global`;
3. lead más antiguo (first touch) al empatar evidencia;
4. ORIGEN en empate final.

`analytics.v_portal_conversion_health.conversiones_duplicadas_error` debe permanecer en `0`.

## Objetos creados

### Staging

- `staging.portal_leads_base`
- `staging.portal_compradores_base`

### Analytics

- `analytics.portal_lead_match`
- `analytics.v_portal_conversion_export`
- `analytics.v_portal_conversion_medio`
- `analytics.v_portal_conversion_medio_total`
- `analytics.v_portal_conversion_cohorte_mensual`
- `analytics.v_portal_conversion_proyecto`
- `analytics.v_portal_conversion_conversiones`
- `analytics.v_portal_conversion_health`

## Refresh

El refresh maestro ejecuta automáticamente el mart después de `staging.clientes_calidad`:

```text
RAW
  ↓
schema_sync
  ↓
staging.clientes_calidad
  ↓
portal conversion attribution
  ↓
CORE / analytics restantes
```

Manual:

```bat
scripts\17_refresh_portal_conversion.bat
```

Dry run:

```powershell
.\.venv\Scripts\python.exe .\scripts\refresh_portal_conversion.py --start-year 2026 --dry-run
```

## Generar Excel

Todos los medios:

```bat
scripts\18_export_portal_conversion_excel.bat all 2026
```

Solo Urbania:

```bat
scripts\18_export_portal_conversion_excel.bat urbania 2026
```

Salida por defecto:

```text
reports/portal_conversion_<medio>_<year>.xlsx
```

Hojas:

- `Dashboard`
- `Cohortes`
- `Match_Origen`
- `Match_Medio_Actual`
- `Conversiones`
- `Metodologia`

## Queries rápidas

```sql
SELECT *
FROM analytics.v_portal_conversion_medio_total
WHERE lead_year = 2026
ORDER BY tasa_conversion DESC NULLS LAST, leads DESC;
```

```sql
SELECT *
FROM analytics.v_portal_conversion_medio
WHERE lead_year = 2026
  AND medio_captacion = 'urbania';
```

```sql
SELECT *
FROM analytics.v_portal_conversion_export
WHERE lead_year = 2026
  AND conversion_atribuida
ORDER BY fecha_separacion DESC;
```

```sql
SELECT * FROM analytics.v_portal_conversion_health;
```
