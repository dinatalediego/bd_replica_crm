# Réplica Redshift → PostgreSQL + Decision Intelligence

Versión **0.2.0**. Mantiene la sincronización incremental de Amazon Redshift hacia PostgreSQL local y agrega una arquitectura para convertir datos en decisiones económicas auditables.

## Arquitectura

```text
Amazon Redshift
      ↓
raw_cygnus                ← réplica confiable
      ↓
staging / analytics       ← negocio y marts
      ↓
features                   ← variables as-of, sin leakage
      ↓
causalidad + predicción    ← qué ocurrirá / qué cambia si actúo
      ↓
economía                   ← valor esperado y costo de oportunidad
      ↓
decision_intelligence      ← recomendación y prioridad
      ↓
acción real
      ↓
outcome
      ↓
aprendizaje
```

## Qué conserva de v0.1.0

- descubrimiento de Redshift;
- cargas incrementales;
- `UPSERT` PostgreSQL;
- lookback para cambios tardíos;
- auditoría de sincronización;
- logs y bloqueo de ejecuciones simultáneas;
- automatización horaria en Windows.

## Qué agrega v0.2.0

- contratos de decisión versionados;
- schemas `features`, `decision_intelligence`, `model_control` y `experiments`;
- registro de modelos, recomendaciones, acciones y outcomes;
- Difference-in-Differences baseline;
- regresión logística probabilística baseline;
- forecast ETS baseline;
- CATE/uplift → valor económico incremental → ranking de acciones;
- restricciones de capacidad;
- feedback loop para medir valor realizado;
- tres contratos iniciales: riesgo de caída, leads y pricing.

## Inicio rápido

```bat
scripts\01_instalar.bat
scripts\02_probar_conexiones.bat
scripts\03_inicializar_postgres.bat
scripts\04_descubrir_tablas.bat
scripts\10_validar_contratos_decision.bat
scripts\11_demo_decisiones.bat
```

La demo no usa información real y genera:

```text
reports\decision_demo.csv
```

## Comandos CLI

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli test-connections
.venv\Scripts\python.exe -m replica_cygnus.cli init
.venv\Scripts\python.exe -m replica_cygnus.cli discover --schema grupocygnus
.venv\Scripts\python.exe -m replica_cygnus.cli validate --only clientes_proyectos --include-disabled
.venv\Scripts\python.exe -m replica_cygnus.cli sync --only clientes_proyectos --include-disabled --max-rows 500
.venv\Scripts\python.exe -m replica_cygnus.cli sync
.venv\Scripts\python.exe -m replica_cygnus.cli status --limit 30
.venv\Scripts\python.exe -m replica_cygnus.cli decision-contracts
.venv\Scripts\python.exe -m replica_cygnus.cli decision-demo
```

## Documentación importante

- `docs/PASO_A_PASO.md`: réplica local.
- `docs/DECISION_INTELLIGENCE.md`: diseño de la nueva capa.
- `docs/ROADMAP_ECONOMISTA_DECISION_SYSTEMS.md`: destrezas y secuencia de proyectos.
- `docs/MIGRACION_v0.1.0_A_v0.2.0.md`: actualización desde la versión anterior.
- `docs/SEGURIDAD_Y_PERMISOS.md`: seguridad de información local.

## Principio central

No se optimiza por accuracy. Se optimiza una **política de decisión**:

```text
probabilidad predictiva
+ efecto causal de actuar
+ impacto económico
+ costo de intervención
+ restricciones
= acción priorizada
```

Por eso un lead con alta probabilidad de compra no necesariamente debe recibir prioridad: puede comprar de todas formas. La prioridad económica está en las entidades donde la intervención genera mayor valor incremental esperado.

## Seguridad

Redshift se trata como origen de lectura. No guardes `.env` ni credenciales en Git. Valida autorización y tratamiento de datos personales antes de persistir información de clientes en un equipo local.

## v0.3.0 — Sprint 1 Control Tower

Esta versión añade `observability` y un paquete Power BI listo para construir el **Medallio Data & Decision Control Tower**.

Inicio rápido después de actualizar:

```bat
scripts\01_instalar.bat
scripts\03_inicializar_postgres.bat
scripts\12_inicializar_observabilidad.bat
scripts\13_observar_ahora.bat
```

Luego revisa `powerbi/POWER_BI_BUILD_STEP_BY_STEP.md`.

La tarea horaria existente que apunta a `scripts\run_hourly.bat` pasa a ejecutar sincronización + snapshot liviano de observabilidad.
