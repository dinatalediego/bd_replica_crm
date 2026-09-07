# Piloto comercial Cygnus: operación v1

Este módulo convierte scores existentes en asignaciones prospectivas y medibles. No envía mensajes, no modifica precios, no activa tareas automáticas y no promueve modelos. Scripts 40–45 conservan su comportamiento. Es una capa aditiva en `experiments.lead_pilot_*`; las tablas genéricas `experiments.assignments` y el feedback observacional siguen independientes.

## Qué queda congelado

Una persona entra una sola vez por piloto, identificada por hash SHA256 de `documento_cliente` con espacios externos removidos. Conserva ceros y signos: comprobar normalización, documentos compartidos/ficticios y duplicados antes de aprobar elegibilidad. El hash es un seudónimo, no anonimización ni protección criptográfica de documentos de baja entropía.

Asignación Bernoulli reproducible mediante hash de piloto + semilla aleatoria fijada de antemano + cliente. Se propone 50/50. No garantiza números exactamente iguales ni es aleatorización por bloques. No elegir/repetir semillas buscando resultados favorables. Se congelan proyecto, asesor, canal, score, probabilidades, modelo y timestamps de ingreso. Reasignaciones del cliente no crean otra unidad experimental. No cambiar modelo ni umbral durante el piloto.

Solo puede haber un piloto ACTIVE. Personas en seguimiento de otros pilotos durante 60 días se rechazan. Un piloto pausado no recluta; puede seguir registrando acciones y resultados. CLOSED no reabre, pero permite completar seguimiento. El sistema registra la política asignada aunque el asesor no la cumpla: el análisis principal es por intención de tratar (ITT).

## Gate comercial y técnico antes de activar

- [ ] Confirmar elegibilidad: permiso de contacto, cliente nuevo o recurrente, proforma/separación previa, exclusiones. El supervisor revisa cada `evidence_key` antes de ingresarlo al CSV.
- [ ] Definir separación a 14 días y minuta a 60 desde asignación experimental, pago inicial, procesos/proforma, caídas y fuentes verificables. No copiar las etiquetas predictivas existentes: parten de otra fecha.
- [ ] Elegir proyectos, score mínimo fijo, modelo y capacidad real de atención. La banda A diaria cambia; este piloto usa umbral numérico congelado.
- [ ] Aprobar protocolo de ambos grupos, SLA y alcance de costos en PEN. Los 60 minutos del ejemplo son una propuesta desde asignación; no una promesa desde creación del lead. Medir también retraso de réplica/scoring.
- [ ] Auditar separación temporal train/test, calibración por cohortes y variables point-in-time. PASS del modelo es evidencia predictiva, no causal ni aprobación del piloto.
- [ ] Fijar tasa base real, efecto mínimo relevante (MDE), potencia, muestra por brazo y fecha máxima de reclutamiento. Un número de leads activos no determina por sí solo potencia suficiente.
- [ ] Elegir UNA hipótesis primaria; separar análisis secundarios y exploratorios. No detener por significancia en revisiones diarias.
- [ ] Verificar duración total = reclutamiento necesario + 14/60 días después de la última asignación + conciliación de datos. Si llega la fecha máxima sin muestra, reportar limitación.

Estos son asuntos de negocio pendientes; el archivo de ejemplo contiene valores nulos y `business_rules_approved=false` y falla al registrarlo hasta completarlos.

## Instalación local explícita

Desde la raíz del repositorio en PowerShell, con el entorno que ya ejecuta scoring:

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py --help
# Dependencias opcionales para pruebas y el notebook (no necesarias para el CLI):
.\.venv\Scripts\python.exe -m pip install -r tests\requirements-pilot.txt
# Aplicar solo en la base local/de pruebas autorizada; usa la configuración PostgreSQL del repo.
.\.venv\Scripts\python.exe scripts\lead_pilot.py init
Copy-Item config\lead_pilot.example.json config\lead_pilot.local.json
```

`init` requiere tablas de lead scoring previamente instaladas. Crea solo nuevas tablas/vistas/índices; se puede repetir. No crea usuarios ni otorga permisos. No ejecutarlo contra producción sin autorización. Usar `statement_timeout=60s`, `lock_timeout=5s`; si falla, el DDL de esa ejecución revierte completo. No reiniciar a ciegas ni lanzar scripts de scoring concurrentes para solucionarlo.

Completar JSON aprobado. `model_run_id` debe existir y tener alias `serving` al activar. Generar semilla con `[guid]::NewGuid().ToString()` y conservarla. `enrollment_end` debe incluir zona horaria, por ejemplo `2026-10-31T18:00:00-05:00` (fecha ilustrativa, no aprobada).

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py create --protocol config\lead_pilot.local.json --operator "responsable"
# Solo después de aprobar el protocolo: esta acción inicia la ventana prospectiva.
.\.venv\Scripts\python.exe scripts\lead_pilot.py state --pilot cygnus_contact_v1 --status ACTIVE --operator "aprobador"
```

El protocolo queda inmutable. Para corregir un diseño registrado, cerrar ese piloto y crear otro identificador con nueva aprobación. No editar tablas directamente para cambiar grupos ni resultados.

## Rutina comercial diaria

1. Ejecutar la réplica y `41_lead_scoring_live.bat`; verificar frescura. Mantener el modelo congelado: no entrenar/promover otro durante reclutamiento sin pausar y revisar el diseño.
2. Revisar candidatos LIVE posteriores a activación y elegibilidad en CRM. Llenar `eligibility.template.csv`: `evidence_key,source_ref`. Referencia de revisión, no teléfonos ni texto privado. Un cliente con varias evidencias se asigna una vez (primera evidencia aprobada por fecha).
3. Previsualizar antes de persistir:

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py enroll --pilot cygnus_contact_v1 --eligibility-csv data\pilot\eligibility.csv --operator "supervisor"
.\.venv\Scripts\python.exe scripts\lead_pilot.py enroll --pilot cygnus_contact_v1 --eligibility-csv data\pilot\eligibility.csv --operator "supervisor" --apply
```

4. El supervisor distribuye `v_lead_pilot_operations`: grupo, protocolo, asesor, `lead_id`, plazo y `assignment_id`. TREATMENT recibe el protocolo aprobado; CONTROL la atención habitual, sin retardarla. No seleccionar solo los tratamientos después de previsualizar; todos los elegibles deben persistirse, aunque el brazo no sea el esperado.
5. Registrar cada intento, también los no respondidos, y acciones del control. Usar `actions.template.csv`. `event_id` UUID estable por evento; generarlo una sola vez. Tipos: CALL, WHATSAPP, VISIT_SCHEDULED, VISIT_COMPLETED, NO_CONTACT. `result` distingue conversación efectiva de intento. SLA mide primer intento CALL/WHATSAPP, no contacto efectivo. Costos no negativos y hasta cuatro decimales; definir si incluyen tiempo del asesor y costo de oportunidad.

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py import --pilot cygnus_contact_v1 --kind actions --csv data\pilot\actions.csv --operator "supervisor"
.\scripts\46_lead_pilot_status.bat cygnus_contact_v1
```

6. Al madurar cada horizonte, conciliar procesos/proformas y llenar `outcomes.template.csv`. Un 1 exige `event_at` en `[assigned_at, assigned_at + horizonte)`; un 0 exige evento vacío y revisión completa. `observed_through` es la cobertura efectiva del extracto, no el momento de pulsar ejecutar; debe cubrir todo el horizonte y no ser futura. `verified_by` identifica al revisor. Este primer adaptador es un CSV revisado: la extracción automática de procesos requiere confirmar las reglas de negocio anteriores.

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py import --pilot cygnus_contact_v1 --kind outcomes --csv data\pilot\outcomes.csv --operator "analista"
```

7. Abrir `notebooks/08_piloto_comercial_monitoreo.ipynb` en VS Code. Por defecto ejecuta DEMO sintética; cambiar a LIVE para leer la base local. No entrena ni escribe a la BD. Revisar faltantes y conciliación antes de interpretar efectos.
8. Al completar muestra en ambos brazos o vencer fecha, se detiene la admisión. Pausar/cerrar explícitamente para liberar la operación, completar seguimiento y revisión final; no declarar ganador automáticamente.

```powershell
.\.venv\Scripts\python.exe scripts\lead_pilot.py state --pilot cygnus_contact_v1 --status PAUSED --operator "supervisor"
```

No duplicar registros entre el comando observacional `lead_scoring.py action` y esta importación. El piloto usa sus propias tablas para preservar asignación y atribución. Mantener CSV operativos fuera de Git y no subir notebooks con datos personales.

## Reintentos, conciliación y rechazos

Lotes aceptan filas válidas y registran rechazos por fila. La igualdad obligatoria es `source_rows = accepted_rows + existing_rows + rejected_rows`. Cada lote persistido tiene UUID; revisar `v_lead_pilot_reconciliation`. No imprimir filas de clientes completas en logs. El CLI retorna 0 si no hay rechazados, 2 si hubo rechazos parciales, 1 para errores de validación de archivo/protocolo. Errores SQL abortan la transacción completa (no registrar éxito).

Reimportar el mismo evento/outcome con idénticos campos cuenta como existente. Cambiar un registro con la misma clave se rechaza como conflicto; resolver mediante revisión documentada, sin sobreescribir automáticamente. Duplicados de `evidence_key` en el CSV de elegibilidad rechazan el archivo entero antes de escribir. Correcciones auditadas de outcomes ya finalizados y costos posteriores quedan como extensión pendiente.

## Power BI

Conector PostgreSQL, base local configurada, modo Import inicial. No se necesita gateway para Desktop local; publicación y gateway corporativo se configuran aparte. Usar credencial de solo lectura autorizada. No se han creado permisos ni publicado un PBIX.

| Vista | Grano y uso |
|---|---|
| `experiments.v_lead_pilot_operations` | Una fila por cliente asignado; cola operativa restringida, incluye lead_id. |
| `experiments.v_lead_pilot_monitor` | Dos filas por asignación, una por endpoint; detalle analítico sin documento. |
| `experiments.v_lead_pilot_summary` | Piloto/brazo/cohorte/proyecto/endpoint; tablero gerencial. |
| `experiments.v_lead_pilot_reconciliation` | Un lote; contabilidad de filas y motivos de rechazo. Restringir acceso. |

En monitor/summary usar selector de endpoint de selección única. No sumar costos, asignados ni acciones entre endpoints: se repetirían. Para cartera total usar operations. Evitar relaciones many-to-many; si se relacionan, operations[assignment_id] 1→N monitor[assignment_id]. Resultados por proyecto/cohorte son exploratorios; el efecto primario se calcula sobre población predefinida completa y madura.

Medidas sobre tabla importada renombrada `PilotSummary`:

```dax
Asignados = IF(HASONEVALUE(PilotSummary[outcome_name]), SUM(PilotSummary[assigned]))
Maduros = IF(HASONEVALUE(PilotSummary[outcome_name]), SUM(PilotSummary[mature]))
Faltantes maduros = IF(HASONEVALUE(PilotSummary[outcome_name]), SUM(PilotSummary[missing_mature]))
Tasa ITT = IF([Maduros] > 0 && [Faltantes maduros] = 0,
    DIVIDE(SUM(PilotSummary[positives]), [Maduros]))
Diferencia pp = VAR T = CALCULATE([Tasa ITT], PilotSummary[arm] = "TREATMENT")
    VAR C = CALCULATE([Tasa ITT], PilotSummary[arm] = "CONTROL")
    RETURN IF(NOT ISBLANK(T) && NOT ISBLANK(C), 100 * (T - C))
```

Página 1: asignados, SLA, demora, acciones, pendientes. Página 2: brazos, maduros, faltantes, tasas y diferencia; intervalos desde notebook. Página 3: lotes y rechazos. Refrescar después de cada importación.

## Evaluación y riesgos

El notebook bloquea estimación completa si falta algún outcome maduro, muestra límites extremos para faltantes y usa intervalos Newcombe para diferencia de proporciones. No comparar únicamente contactados: eso rompe la aleatorización. El conteo de acciones no demuestra efecto causal. AUC y Brier describen predicción; no ventas incrementales.

Fórmula económica una vez verificadas minutas y costos comparables: margen incremental por cliente = diferencia de tasa de minuta × margen de contribución por minuta − diferencia de costo por cliente. No usar precio de venta como margen ni descontar costos dos veces. El notebook deja inputs económicos pendientes; no inventa rentabilidad.

Revisar contaminación entre asesores/proyectos, adherencia en control y tratamiento, identidad persistente y posibles interferencias por capacidad compartida. La aleatorización por cliente estima la política entre clientes elegibles del umbral aprobado, no uplift individual ni efecto universal de usar ML. La latencia de scoring limita el SLA factible. Con eventos raros puede requerirse una muestra grande; validar potencia y fechas antes de activar.

Referencias técnicas: [bloqueos de PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html), [intervalos para dos proporciones](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.confint_proportions_2indep.html).
