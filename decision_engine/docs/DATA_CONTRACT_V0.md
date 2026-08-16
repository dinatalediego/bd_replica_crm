# Data Contract v0 — Separation Fall Risk

## Decision timestamp

Una observación representa exactamente lo que era conocido en `observed_at`. Ninguna columna puede derivarse de eventos posteriores.

## Grain

Una fila por separación/ciclo comercial activo en el instante de decisión.

## Candidate source

La vista debe construirse sobre el ciclo comercial reconciliado y fuentes analíticas confiables. No se debe inferir el estado de venta desde una sola fila RAW.

## Required identifiers

- `separation_id` o clave estable equivalente;
- `codigo_proforma`;
- `codigo_unidad`;
- `codigo_proyecto`;
- `observed_at`.

## Baseline features

- `days_since_separation`;
- `days_since_last_interaction`;
- `interaction_count_14d`;
- `has_pending_admin_block`.

## Candidate model features

### Lead/client
- antigüedad del lead;
- interacciones 7/14/30d;
- diversidad de canales;
- velocidad entre etapas;
- historial de reactivación.

### Commercial cycle
- edad de separación;
- documentación/administración pendiente;
- cambios de unidad/proforma;
- número de anulaciones previas;
- avance hacia minuta.

### Product/project
- tipología;
- dormitorios;
- piso;
- precio/m2 relativo;
- antigüedad de unidad en stock;
- absorción 30/90d del proyecto;
- stock competidor interno comparable.

### Advisor
- carga activa;
- conversión histórica point-in-time;
- tiempo de respuesta;
- etapa donde suele perder oportunidades.

## Label

Para una observación en `t`, `falls_before_sale_within_30d = 1` si la separación cae antes de venta canónica dentro de los siguientes 30 días. Casos censurados o no reconciliados deben tratarse explícitamente; no forzarlos a 0.

## Splits

- train: ventanas antiguas;
- validation: ventana posterior;
- test: ventana más reciente nunca utilizada para tuning.

Prohibido random split como validación principal.

## Quality gates

Bloquear la recomendación si:

- el ciclo comercial no está reconciliado;
- falta la identidad estable de unidad/proforma;
- hay inconsistencia temporal material;
- la unidad aparece simultáneamente en estados físicos incompatibles;
- el snapshot usa datos posteriores a `observed_at`.

## Metrics

Técnicas: PR-AUC, recall@top-k, Brier/calibration.

Operativas: caídas detectadas en top-N, llamadas/intervenciones por asesor.

Económicas: margen/ventas preservadas por intervención menos costo operativo incremental.
