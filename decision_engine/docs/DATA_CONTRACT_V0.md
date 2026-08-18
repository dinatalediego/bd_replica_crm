# Data Contract v0 — Separation Fall Risk

## Decision timestamp

Una observación representa exactamente lo que era conocido en `observed_at`. Ninguna columna puede derivarse de eventos posteriores.

## Grain

Una fila por separación/ciclo comercial activo y elegible en el instante de decisión.

## Candidate source

La vista se construye sobre el ciclo comercial reconciliado y fuentes analíticas confiables. No se infiere el estado de venta desde una sola fila RAW.

## Eligibility — proformas recientes

El motor de recomendaciones se limita deliberadamente a ciclos cuya proforma sea reciente para evitar que oportunidades históricas o abandonadas generen recomendaciones espurias.

Regla operativa v0.2:

- el ciclo debe estar `ABIERTA` y la separación actual debe estar `Activo`;
- `proforma_first_seen_at` se define como `MIN(raw_cygnus.proforma_unidad.fecha_creacion)` por `codigo_proforma`;
- la proforma es elegible si `proforma_first_seen_at >= observed_at - interval '3 months'` y `proforma_first_seen_at <= observed_at`;
- el límite de exactamente tres meses se incluye;
- se usan **3 meses calendario**, no una aproximación fija de 90 días.

Se usa `MIN(fecha_creacion)` de forma conservadora. Si una proforma antigua adquiere después otra fila/unidad o un duplicado reciente, ese evento posterior no debe rejuvenecer artificialmente la proforma.

Los ciclos abiertos fuera de la ventana permanecen visibles en `features.v_separation_fall_risk_candidate_universe`, pero no llegan a `features.separation_fall_risk_current` ni al scoring.

## Required identifiers and eligibility evidence

- `separation_id` o clave estable equivalente;
- `codigo_proforma`;
- `codigo_unidad`;
- `codigo_proyecto`;
- `observed_at`;
- `proforma_first_seen_at`;
- `proforma_age_days`;
- `eligibility_rule`;
- `eligibility_window_months`.

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
- hay candidatos duplicados;
- un candidato actual queda fuera de la regla de tres meses;
- `proforma_first_seen_at > observed_at`;
- falta `observed_at`;
- hay inconsistencia temporal material;
- la unidad aparece simultáneamente en estados físicos incompatibles;
- el snapshot usa datos posteriores a `observed_at`.

No son fallos del modelo:

- una proforma mayor a tres meses: se excluye por diseño y se contabiliza;
- una proforma sin fecha observable: se excluye y se reporta como deuda de completitud, pero no se fuerza dentro del scoring.

## Quality metrics mínimas

Antes de cada corrida se monitorean al menos:

- universo abierto/activo antes del filtro;
- candidatos elegibles después del filtro;
- exclusiones por proforma mayor a tres meses;
- exclusiones por fecha de proforma faltante;
- proformas posteriores a `observed_at`;
- candidatos actuales fuera de la ventana declarada;
- duplicados;
- `BLOCKED`;
- `observed_at` faltante.

## Metrics

Técnicas: PR-AUC, recall@top-k, Brier/calibration.

Operativas: caídas detectadas en top-N, llamadas/intervenciones por asesor.

Económicas: margen/ventas preservadas por intervención menos costo operativo incremental.
