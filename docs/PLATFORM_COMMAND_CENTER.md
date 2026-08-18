# Cygnus Platform Command Center

## Propósito

Convertir el seguimiento de la plataforma de Inteligencia Comercial en un sistema verificable. El readiness deja de ser un porcentaje manual: los controles que pueden demostrarse desde PostgreSQL o Git se recalculan automáticamente y los componentes externos mantienen controles manuales hasta que tengan integración propia.

## Arquitectura

```text
Redshift -> Python ETL -> PostgreSQL
                         |-- observability
                         |-- model_control
                         |-- decision_intelligence
                         `-- platform_control
                                  |
                                  `-> Power BI / Excel / CLI

Git local ------------------------^
```

## Objetos PostgreSQL

- `platform_control.application_registry`: catálogo de aplicaciones y ownership.
- `platform_control.readiness_controls`: controles ponderados con evidencia.
- `platform_control.milestones`: gates cross-app.
- `platform_control.v_application_readiness`: score y semáforo por aplicación.
- `platform_control.v_platform_summary`: KPIs agregados de la plataforma.

## Scoring

- `DONE` = 1.0
- `IN_PROGRESS` = 0.5
- `BLOCKED` = 0.1
- `NOT_STARTED` = 0.0

El score de aplicación es el promedio ponderado de sus controles.

Semáforo:

- `GREEN`: readiness >= 80% y sin controles bloqueados.
- `AMBER`: readiness >= 40% y sin controles bloqueados.
- `RED`: existe al menos un control bloqueado.
- `GRAY`: readiness < 40% o todavía no existe evidencia suficiente.

## Uso desde VS Code

Desde la raíz del repositorio, con el entorno virtual activo:

```powershell
pip install -e .
python scripts/platform_command_center.py init
python scripts/platform_command_center.py refresh
python scripts/platform_command_center.py status
```

Cada ejecución de `status` genera además:

```text
reports/platform_command_center.csv
```

Ese CSV puede ser consumido inmediatamente por Power BI o Excel. En la siguiente fase puede reemplazarse por conexión directa a las vistas PostgreSQL.

## Controles automáticos iniciales

### PostgreSQL

- schemas mínimos de la plataforma;
- observabilidad;
- gobierno de ML;
- Decision Intelligence;
- tabla de control ETL;
- sincronización exitosa reciente;
- asset registry;
- snapshots y quality checks;
- vistas destinadas al Control Tower.

### Git

- repositorio detectable;
- protección de archivos `.env.*`;
- existencia de tests;
- packaging con `pyproject.toml`;
- CLI instalable.

### Manuales por ahora

- dbt Core;
- Airflow;
- MLflow como servicio;
- Colab Pro;
- Object Storage;
- pgvector / Prismare;
- readiness de FastAPI.

Estos controles deben automatizarse cuando el componente sea desplegado, no antes.

## Gate M01

No priorizar dbt/Airflow como infraestructura adicional hasta demostrar primero:

1. PostgreSQL con capas mínimas gobernadas.
2. Pipeline idempotente con runs auditables.
3. Reconciliación source-target.
4. Data Quality mínimo viable.
5. Definiciones de negocio críticas aprobadas.

Esto mantiene la plataforma incremental y evita sobrearquitectura.
