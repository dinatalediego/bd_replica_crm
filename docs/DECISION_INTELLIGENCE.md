# Decision Intelligence v0.2.0

## Objetivo

La v0.2.0 convierte la réplica local en una base para sistemas de decisión:

```text
Redshift
  ↓
raw_cygnus
  ↓
staging / analytics
  ↓
features
  ↓
causalidad + predicción
  ↓
economía / valor esperado
  ↓
decision_intelligence
  ↓
acción humana o automática
  ↓
outcome observado
  ↓
aprendizaje / recalibración
```

La regla de diseño es: **ningún modelo se crea sin una decisión explícita que mejorar**.

## El contrato de decisión

Cada caso de uso debe declarar:

1. `objective`: qué resultado económico se quiere mejorar.
2. `decision_unit`: sobre qué entidad se decide.
3. `decision_owner`: quién tiene autoridad para ejecutar la acción.
4. `available_actions`: acciones realmente posibles.
5. `target`: qué evento se predice.
6. `prediction_horizon_days`: cuándo importa el evento.
7. `causal_estimand`: qué efecto de una acción se quiere estimar.
8. `primary_value_metric`: cómo se convierte la decisión en valor económico.
9. `feedback_outcome`: qué dato posterior permite aprender si funcionó.
10. `constraints`: capacidad, presupuesto, reglas comerciales y aprobaciones.

Los contratos iniciales viven en `config/decision_systems.yml`.

## Capas PostgreSQL

### `raw_cygnus`
Copia de datos de origen. No contiene lógica de negocio compleja.

### `staging`
Normalización, deduplicación, tipado y limpieza.

### `analytics`
Hechos, dimensiones y marts de negocio.

### `features`
Variables con definición temporal explícita para modelos. Cada feature debe evitar leakage.

### `model_control`
Registro de entrenamientos, versiones, ventanas temporales, features, parámetros y métricas.

### `decision_intelligence`
Recomendaciones, acciones efectivamente tomadas y outcomes posteriores.

### `experiments`
Diseños de experimentación o cuasi-experimentación y asignaciones de tratamiento.

## Flujo de una decisión

Ejemplo: priorización de leads.

```text
lead
 ↓
P(separación en 14d | información disponible hoy)
 ↓
CATE(contacto temprano) = cambio esperado en esa probabilidad
 ↓
valor incremental esperado = beneficio incremental - costos
 ↓
restricción: 25 llamadas por asesor/día
 ↓
ranking por valor incremental
 ↓
CALL / NURTURE / NO_ACTUAR
 ↓
acción registrada
 ↓
separación observada o no
 ↓
evaluación de calibración + valor realizado + efecto causal
```

## Qué significa cada bloque cuantitativo

### Predicción
Responde: **¿qué probablemente ocurrirá?**

La v0.2.0 incluye un baseline interpretable con regresión logística. Debe validarse temporalmente; no usar random split cuando el objetivo sea producción sobre datos futuros.

### Causalidad
Responde: **¿qué cambiaría si actuamos?**

La v0.2.0 incluye Difference-in-Differences como baseline didáctico y operativo. No convierte automáticamente una asociación en causalidad: se deben justificar tendencias paralelas, tratamiento, timing y ausencia de shocks diferenciales relevantes.

### Economía
Responde: **¿vale la pena actuar?**

El motor compara valor esperado de no actuar contra valor esperado de actuar, incluyendo:

- probabilidad base;
- efecto causal incremental;
- valor de éxito;
- pérdida por fracaso;
- costo directo de la acción;
- costo de oportunidad.

### Decisión
Responde: **¿qué acción hacemos primero dadas las restricciones?**

La v0.2.0 prioriza por valor incremental esperado y puede imponer una capacidad máxima de acciones.

### Aprendizaje
Responde: **¿la decisión realmente produjo valor?**

Se registra por separado:

- recomendación;
- acción efectivamente tomada;
- outcome posterior;
- valor realizado.

Esta separación permite distinguir error del modelo, incumplimiento de la recomendación y una acción que fue ejecutada pero no tuvo el efecto esperado.

## Comandos

Después de instalar/actualizar:

```bat
scripts\03_inicializar_postgres.bat
scripts\10_validar_contratos_decision.bat
scripts\11_demo_decisiones.bat
```

La demo genera:

```text
reports\decision_demo.csv
```

Incluye por entidad:

- probabilidad predictiva;
- CATE sintético;
- valor esperado sin actuar;
- valor incremental de actuar;
- valor esperado con acción;
- acción recomendada;
- ranking de prioridad.

## Tres casos de uso iniciales

### 1. Riesgo de caída de separaciones

No priorizar por `P(caída)` solamente. Priorizar por el valor esperado de una intervención que pueda evitarla.

### 2. Leads

No confundir propensión con persuadibilidad. Un lead con 90% de probabilidad de separar sin intervención puede tener menor valor incremental de contacto que otro con 45% cuyo uplift sea alto.

### 3. Pricing

No usar solamente un forecast de ventas. El objetivo es estimar la respuesta causal al precio/descuento y optimizar margen/absorción sujeto a reglas de coherencia y aprobación.

## Principios de diseño permanentes

1. La unidad temporal de cada feature debe ser anterior a la decisión.
2. La predicción no sustituye un estimando causal.
3. La utilidad económica debe estar separada del score estadístico.
4. Toda recomendación debe poder auditarse.
5. Toda acción real debe registrarse, incluso cuando contradice el modelo.
6. Todo outcome debe cerrar el feedback loop.
7. La evaluación debe incluir métricas estadísticas y económicas.
8. Los modelos deben compararse contra una política baseline, no contra “no tener modelo”.
