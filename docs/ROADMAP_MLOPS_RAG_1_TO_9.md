# Ejecución 1–9 — DW, MLOps, acción, impacto y RAG

## North Star

Aumentar ventas y margen mediante decisiones comerciales trazables, con control
humano y aprendizaje basado en outcomes observados.

| Paso | Gate / entregable | Estado en el repositorio | Próxima evidencia requerida |
|---:|---|---|---|
| 1 | Funnel y datasets analíticos certificados | En progreso: CORE comercial y ciclo certificado existen | Validar definición oficial de caída y reglas de pago de inicial ≥5% |
| 2 | Baseline en notebook o script reproducible | Implementado como regresión logística temporal | Ejecutar con `medallio_dw` real y conservar métricas/resultados |
| 3 | Baseline convertido en paquete Python | Implementado en `replica_cygnus.lead_scoring` | Validar instalación limpia en PC operativa |
| 4 | MLflow Tracking | Pendiente | Backend PostgreSQL, artifacts fuera de Git y primer run trazable |
| 5 | Registry candidate/champion | Implementado con registry propio; migración MLflow pendiente | Conciliar aliases propios con MLflow sin doble fuente de verdad |
| 6 | Scoring batch hacia PostgreSQL/Power BI | Implementado | Ejecutar ciclo real y validar filas/bandas/freshness |
| 7 | Acciones y outcomes | Implementado en v0.2; no ejecutado contra DW real | Registrar primeras acciones y esperar maduración 14/60 días |
| 8 | Impacto incremental | Pendiente | Diseñar elegibilidad, tratamiento/control y métrica de margen |
| 9 | RAG gerencial con citas | Pendiente | Inventario y versionado de reglas, campañas y decisiones |

## Paso 1 — contrato del funnel

Grano principal: `codigo_proforma` para ciclo comercial y `evidence_key` para
decisión de priorización.

Debe quedar versionado:

- separación válida y su fecha;
- pago de inicial desde 5%;
- venta/minuta;
- caída y motivo;
- relación cliente–proforma–unidad–proyecto;
- timestamp disponible al decidir.

No se fusionarán variantes de definición hasta resolverlas como contrato.

## Paso 2 — baseline

Mantener un modelo explicable y una regla simple como comparator. La evaluación
es out-of-time y reporta AUC, Brier y conversión dentro del top 20%.

## Paso 3 — paquete

El mismo código debe operar desde pruebas, CLI, tarea programada y notebook. El
notebook es exploración; el paquete es la implementación reproducible.

## Paso 4 — MLflow Tracking

Configurar después de ejecutar el primer ciclo real. Registrar:

- Git SHA;
- dataset y ventana temporal;
- target/features;
- parámetros y métricas;
- artifact URI;
- decision system.

No guardar artifacts ni secretos en Git. DEV puede ser local; producción no debe
depender de una PC personal.

## Paso 5 — registry

El registry propio permanece como contrato operacional hasta que MLflow pueda
reproducir `candidate`, `champion`, `serving`, aprobación y rollback. Durante la
migración habrá una sola autoridad efectiva por alias.

## Paso 6 — scoring batch

Operación inicial diaria. Tiempo real no es necesario para demostrar valor.
Controlar cobertura, freshness, drift y distribución por bandas.

## Paso 7 — acción y outcome

Usar `docs/LEAD_ACTION_OUTCOME_LOOP.md`. Ninguna acción es automática. Medir
adopción, separación 14d, minuta 60d, costo y trazabilidad por recomendación.

## Paso 8 — impacto incremental

Antes de estimar uplift, registrar:

- población elegible;
- asignación tratamiento/control;
- acción realmente ejecutada;
- contaminación o incumplimiento;
- costo;
- separación, inicial, venta y margen.

Primera pregunta causal: “¿contactar con prioridad alta incrementa la minuta a
60 días frente a la operación habitual entre leads elegibles?”

## Paso 9 — RAG

RAG recuperará definiciones, políticas, campañas, decisiones y evidencia. Las
cifras se consultarán en vistas gobernadas de PostgreSQL; el LLM no calculará
KPIs leyendo documentos. Cada respuesta debe incluir fecha de corte, fuentes y
versión de regla.

## Orden operativo inmediato

1. Ejecutar el SQL aditivo de lead scoring en `medallio_dw`.
2. Ejecutar `41_lead_scoring_live.bat`.
3. Reconciliar scores y recomendaciones.
4. Registrar acciones reales durante operación.
5. Medir cobertura inmediatamente y conversión al madurar 14/60 días.
6. Solo entonces instalar MLflow y registrar el run ya validado.
