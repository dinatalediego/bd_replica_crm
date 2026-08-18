# Data Contract v0 — Separation Fall Risk

## Decision timestamp

Una observación representa exactamente lo conocido en `observed_at`. Ninguna feature puede usar eventos posteriores.

## Grain

Una fila por separación/ciclo comercial activo y elegible en el instante de decisión.

## Candidate source

El motor parte del ciclo comercial reconciliado en CORE. No reconstruye el estado de venta desde una fila RAW aislada.

## Conversión comercial autoritativa

La recomendación busca intervenir únicamente sobre oportunidades que **todavía no han demostrado conversión**. El profiling de `datos_extras` fijó dos campos distintos:

- `nombre='fecha_de_minuta'`: campo de fecha. En el Power Query de negocio corresponde a `Fecha_PagoCI_pm`; CORE lo expone como `fecha_pago_ci`.
- `nombre='pago_ci'`: marcador categórico, **no fecha**. El valor positivo actualmente conocido es `Pagó cuota inicial (Minuta)`.

Los campos no tienen obligación de coexistir. En el profiling de 2026-08-18 se observaron marcadores sin fecha y fechas sin marcador.

### Regla de fecha de venta

```text
Fecha_Venta = COALESCE(
    fecha_de_minuta,
    IF(Fecha_Separacion < 2026-01-01, Fecha_Proceso_Venta, NULL)
)
```

- `fecha_de_minuta` tiene prioridad como fecha efectiva de conversión.
- Antes de `2026-01-01`, si no existe fecha efectiva, la fecha del proceso `Venta` es fallback legacy.
- Desde `2026-01-01`, la fecha del proceso `Venta` significa cierre del proceso comercial, no evidencia suficiente de conversión.

### Marcador `pago_ci`

- `Pagó cuota inicial (Minuta)` es evidencia positiva de conversión.
- Si existe marcador positivo pero falta `fecha_de_minuta`, el registro tiene conversión conocida pero precisión temporal incompleta.
- Ese caso **no entra al risk scoring**. Se excluye y se reporta como deuda de calidad; nunca se interpreta como “no pagó”.
- Un valor no vacío de `pago_ci` distinto del marcador conocido es semántica desconocida y se aísla.

## Eligibility — proformas recientes y sin Entrega activa

Regla operativa v0.4:

- el ciclo debe estar `ABIERTA` y la separación actual `Activo`;
- no debe existir un proceso `Entrega` con `estado='Activo'` para el mismo par `codigo_proforma + codigo_unidad`;
- `proforma_first_seen_at = MIN(raw_cygnus.proforma_unidad.fecha_creacion)` por `codigo_proforma`;
- la proforma debe caer entre `observed_at - interval '3 months'` y `observed_at`, inclusive;
- se usan 3 meses calendario, no 90 días;
- una proforma antigua no se rejuvenece por nuevas filas posteriores;
- cualquier marcador positivo `pago_ci` excluye la oportunidad del scoring;
- un marcador desconocido queda en bucket bloqueado y tampoco llega al scoring.

La exclusión por `Entrega Activa` se resuelve en el grain comercial `codigo_proforma + codigo_unidad`, no por `procesos.id`, porque `procesos.id` no es globalmente único entre namespaces de proceso. Las filas de Entrega se agregan antes del join para impedir que duplicados de origen multipliquen candidatos.

`features.v_separation_fall_risk_candidate_universe` conserva todos los buckets; `features.separation_fall_risk_current` contiene solo `ELIGIBLE`.

## Baseline features

- `days_since_separation`;
- `days_since_last_interaction`;
- `interaction_count_14d`;
- `has_pending_admin_block`.

Limitaciones v0.4:

- `interaction_count_14d` es proxy binario 0/1 basado en la interacción más reciente cliente-proyecto;
- `has_pending_admin_block` permanece `NULL` hasta certificar la regla administrativa.

## Label futuro

Para una observación en `t`, `falls_before_sale_within_30d = 1` si ocurre caída antes de la venta canónica dentro de los siguientes 30 días. Casos con marcador positivo pero sin fecha de conversión deben tratarse como censurados/indeterminados temporalmente, nunca forzarse a 0 o 1 sin regla explícita.

## Splits

- train: ventanas antiguas;
- validation: ventana posterior;
- test: ventana más reciente nunca usada para tuning;
- no usar random split como validación principal.

## Quality gates

Bloquear o excluir de forma segura si:

- el ciclo no está reconciliado;
- falta identidad estable unidad/proforma;
- hay candidatos duplicados;
- un candidato sale de la ventana de 3 meses;
- `proforma_first_seen_at > observed_at`;
- falta `observed_at`;
- existe un proceso `Entrega Activo` dentro del conjunto que llegó al scoring;
- existe `fecha_de_minuta` no parseable;
- una `ABIERTA` residencial tiene `fecha_pago_ci` válida;
- una venta residencial post-2026 usa evidencia distinta de `FECHA_DE_MINUTA`;
- un candidato actual contiene marcador `pago_ci` positivo o desconocido;
- existe inconsistencia temporal material (`fecha_venta < fecha_separacion`, etc.);
- el snapshot usa datos posteriores a `observed_at`.

No son fallos del modelo si están explicitados y excluidos:

- proceso `Entrega Activo`: exclusión operativa por diseño;
- proforma mayor a 3 meses;
- proforma sin fecha observable;
- marcador positivo `pago_ci` sin `fecha_de_minuta`: es deuda de precisión temporal, pero evidencia suficiente para no recomendar riesgo.

## Quality metrics mínimas

Antes de cada corrida se monitorean:

- universo abierto/activo;
- candidatos elegibles;
- exclusiones por proceso `Entrega Activo`;
- candidatos actuales que todavía contienen un `Entrega Activo` —debe ser 0;
- exclusiones por antigüedad;
- exclusiones por fecha de proforma faltante;
- exclusiones por marcador positivo `pago_ci`;
- marcadores `pago_ci` desconocidos;
- candidatos que aún contienen cualquier marcador;
- `fecha_de_minuta` no parseable;
- marcadores positivos sin fecha efectiva;
- fechas efectivas sin marcador;
- duplicados y `BLOCKED`;
- ventas por `FECHA_DE_MINUTA`;
- ventas legacy pre-2026;
- ventas post-2026 sin fecha efectiva.

### Reconciliación del universo

Cada fila del universo debe caer en exactamente un bucket:

```text
universo abierto/activo
=
ELIGIBLE
+ EXCLUDED_ACTIVE_ENTREGA_PROCESS
+ EXCLUDED_PROFORMA_OLDER_THAN_3_MONTHS
+ BLOCKED_MISSING_PROFORMA_DATE
+ BLOCKED_PROFORMA_AFTER_OBSERVED_AT
+ BLOCKED_MISSING_OBSERVED_AT
+ EXCLUDED_PAGO_CI_MARKER_CONFIRMED
+ BLOCKED_UNKNOWN_PAGO_CI_MARKER
```

Si la igualdad no se cumple, la corrida se bloquea.

## Métricas del modelo

Técnicas: PR-AUC, recall@top-k, Brier/calibration.

Operativas: caídas detectadas en top-N, intervenciones por asesor, precisión del top-N.

Económicas: ventas/margen preservados por intervención menos costo operativo incremental.
