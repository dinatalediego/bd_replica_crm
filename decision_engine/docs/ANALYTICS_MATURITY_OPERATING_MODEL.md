# Analytics & Decision Intelligence Operating Model

## North Star

La madurez no se mide por cantidad de dashboards, modelos o notebooks. Se mide por la capacidad de convertir datos confiables en decisiones repetibles, medibles y mejorables.

**North Star:**

`valor económico incremental realizado por decisiones asistidas / periodo`

Una decisión solo se considera productiva cuando existe una cadena trazable:

`fuente -> réplica -> contrato -> feature point-in-time -> policy/modelo -> recomendación -> acción -> outcome -> aprendizaje`

---

## Modelo de madurez objetivo

### Nivel 0 — Reporting reactivo
- métricas reconstruidas en cada reporte;
- validación manual;
- poca trazabilidad;
- decisiones dependen de interpretación individual.

### Nivel 1 — Data foundation confiable
- réplica automatizada e idempotente;
- llaves certificadas por tabla;
- contratos de granularidad;
- reconciliación origen-destino;
- observabilidad y lineage mínimo;
- semantic/core layer estable.

**Gate:** ninguna capa analítica puede compensar silenciosamente pérdida de granularidad en RAW.

### Nivel 2 — Analytics gobernado
- métricas canónicas;
- dimensiones conformadas;
- datasets certificados;
- tests de calidad automatizados;
- snapshots point-in-time;
- SLAs/SLOs de frescura, completitud y exactitud.

### Nivel 3 — Decision Intelligence
- decisiones registradas como productos;
- owner, entidad, cadence, action space y outcome definidos;
- baseline explicable obligatorio;
- quality gates antes del scoring;
- recomendaciones trazables;
- human-in-the-loop;
- feedback y outcome obligatorios.

### Nivel 4 — Data Science productivo
- backtesting temporal;
- champion/challenger;
- calibración;
- drift monitoring;
- shadow deployment;
- model/policy registry;
- promoción/retiro con criterios objetivos;
- medición de valor incremental.

### Nivel 5 — Experimentación y optimización
- experimentos controlados;
- causalidad/uplift;
- optimización con restricciones de negocio;
- asignación de recursos;
- pricing/marketing/action policies adaptativas;
- aprendizaje continuo con governance.

---

## Los 8 dominios corporativos de madurez

| Dominio | Pregunta de control | Evidencia esperada |
|---|---|---|
| Data Reliability | ¿La copia representa al origen sin pérdida? | key contracts, parity, freshness, idempotencia |
| Semantic Governance | ¿Qué significa cada métrica? | CORE, diccionario, ownership, versionado |
| Quality & Observability | ¿Sabemos cuándo no confiar? | gates, SLOs, incident log, health views |
| Decision Products | ¿Qué decisión cambia? | decision contract, action space, owner, cadence |
| Data Science | ¿Supera una regla simple? | temporal backtest, calibration, baseline comparison |
| Experimentation | ¿Causa mejora? | holdout/A-B/uplift, pre-analysis plan |
| MLOps / PolicyOps | ¿Puede operarse y retirarse de forma segura? | registry, shadow mode, run log, rollback |
| Value Management | ¿Cuánto valor realizó? | adoption, outcomes, incremental value, cost-to-serve |

---

## Non-negotiables

1. **No leakage.** Ninguna feature puede usar información posterior a `observed_at`.
2. **No silent loss.** Diferencias de granularidad entre origen y réplica bloquean downstream.
3. **Baseline antes de ML.** Un modelo debe superar una política simple en una métrica de negocio.
4. **Shadow antes de live.** Toda policy nueva observa antes de intervenir.
5. **Outcome antes de scale.** No se amplía una decisión si no existe forma confiable de saber qué ocurrió.
6. **Human-in-the-loop en v0.x.** Las recomendaciones comerciales no ejecutan acciones irreversibles.
7. **Version everything.** Contract, feature set, policy, thresholds y schema deben ser identificables.
8. **Reconciliación contable del universo.** Cada entidad debe estar en un bucket explícito: elegible, excluida o bloqueada.
9. **Rollback diseñado antes del release.** Si no puede retirarse rápido, no está listo.
10. **Valor económico > métrica de ML.** AUC/F1 son diagnósticos, no North Star.

---

## Corporate release gates para una decisión

### Gate A — Data contract
- llave fuente certificada;
- paridad origen-destino;
- 0 duplicados por grain canónico;
- 0 pérdida silenciosa;
- freshness dentro del SLO.

### Gate B — Point-in-time correctness
- `observed_at` no nulo;
- no future features;
- eventos posteriores excluidos;
- backtest reconstruible con datos conocidos en ese instante.

### Gate C — Candidate safety
- universo reconciliado;
- exclusiones explícitas;
- 0 entidades ya convertidas dentro del scoring;
- 0 estados incompatibles con la acción recomendada.

### Gate D — Baseline validity
- policy determinista;
- explanation por recomendación;
- ranking estable;
- tests unitarios y contract tests verdes.

### Gate E — Shadow readiness
- recomendaciones persistibles con `mode=SHADOW`;
- ninguna acción automática;
- adopción/feedback capturable;
- run-level audit disponible.

### Gate F — Evidence of value
- outcome coverage suficiente;
- comparación contra baseline/control;
- evidencia de reducción de caídas / aumento de conversión / valor esperado;
- no degradación material por proyecto, asesor o cohorte.

### Gate G — Live promotion
- owner de negocio aprueba;
- owner técnico aprueba;
- rollback probado;
- policy registrada como ACTIVE;
- monitor diario y revisión periódica definidos.

---

## Roles mínimos — equipo corporativo pequeño

### Analytics / Decision Intelligence Lead
- prioriza decisiones;
- define semantic contracts;
- traduce impacto a gerencia;
- aprueba promoción junto con negocio.

### Analytics Engineer / Data Engineer
- ingestión;
- grain/keys;
- data contracts;
- CORE;
- tests y observabilidad.

### Data Scientist / Decision Scientist
- baseline;
- feature design;
- temporal evaluation;
- model/policy;
- causalidad y uplift.

### BI / Analytics Developer
- worklists;
- operational dashboards;
- executive scorecards;
- adoption measurement.

### Business Owner
- valida action space;
- ejecuta/rechaza recomendaciones;
- define costo/beneficio;
- responde por outcomes operativos.

En un equipo pequeño una persona puede cubrir más de un rol, pero **las responsabilidades no deben desaparecer**.

---

## Cadencia operativa recomendada

### Cada ejecución
- data quality gate;
- policy run log;
- candidate reconciliation;
- recommendation snapshot.

### Diario
- freshness;
- candidatos;
- bloqueos;
- recommendation distribution;
- worklist aging;
- fallas de pipeline.

### Semanal
- adopción de recomendaciones;
- outcome coverage;
- top false positives/negatives conocidos;
- concentración por asesor/proyecto;
- incidentes y deuda de datos.

### Mensual
- valor realizado;
- policy performance por cohorte;
- baseline vs champion;
- drift;
- decisiones a promover, pausar o retirar;
- maturity scorecard para gerencia.

### Trimestral
- portfolio review de decisiones;
- roadmap;
- capacidad de equipo;
- arquitectura y costos;
- riesgo/model governance.

---

## SLO inicial sugerido

| SLO | Objetivo inicial |
|---|---:|
| réplica crítica exitosa | >= 99% de runs |
| freshness RAW crítico | <= 90 min |
| duplicados grain certificado | 0 |
| discrepancia origen-destino en key count crítico | 0 |
| recommendations con `observed_at` | 100% |
| recommendations con feature snapshot | 100% |
| recommendations con policy_version | 100% |
| candidates BLOCKED que llegan a scoring | 0 |
| outcome coverage a horizonte cumplido | >= 90% |
| policy live sin run audit | 0 |

Los targets deben endurecerse cuando exista histórico operativo.

---

## Portfolio de decisiones: orden de industrialización

1. `separation_fall_risk` — primera decisión end-to-end.
2. `lead_daily_priority` — productividad comercial diaria.
3. `stock_aging_risk` — inventario y pricing.
4. `monthly_target_forecast` — gestión gerencial.
5. `absorption_deviation` — proyecto / portafolio.
6. matching lead x asesor.
7. matching lead x proyecto/unidad.
8. pricing y descuento en shadow mode.
9. marketing incrementality y budget allocation.

No se inicia una decisión nueva si la anterior todavía no captura outcome de forma confiable, salvo trabajo paralelo explícitamente presupuestado.

---

## Qué significa “listo para gerencia”

Un gerente no necesita ver tablas técnicas. Debe poder responder en menos de un minuto:

1. ¿Qué decisión estamos mejorando?
2. ¿Cuántos casos requieren intervención?
3. ¿Por qué confiamos en el universo?
4. ¿Qué acción recomendamos?
5. ¿Qué pasa si actuamos o no actuamos?
6. ¿Qué valor medimos?
7. ¿Cómo sabemos si el sistema se equivocó?

La plataforma técnica existe para que esas siete respuestas sean defendibles.
