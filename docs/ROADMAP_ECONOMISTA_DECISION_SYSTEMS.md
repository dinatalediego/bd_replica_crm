# Roadmap técnico para un Economista orientado a Decision Systems

## Norte

Construir una ventaja profesional en la intersección:

```text
DATA ENGINEERING
      +
ECONOMETRÍA / CAUSALIDAD
      +
PREDICCIÓN
      +
MICROECONOMÍA / PRICING
      +
OPTIMIZACIÓN
      +
DECISION ENGINEERING
```

## Nivel 1 — Instrumentar correctamente el negocio

Dominar:

- grain, keys, events y estados;
- modelos dimensionales;
- snapshots;
- data quality;
- lineage y timestamps;
- idempotencia;
- incremental loads;
- feature leakage temporal.

Entregable: una réplica reproducible y un warehouse donde cada KPI pueda reconstruirse históricamente.

## Nivel 2 — Diseñar métricas económicas

Dominar:

- unit economics;
- margen y contribución;
- costo de oportunidad;
- valor esperado;
- funciones de pérdida;
- restricciones de capacidad;
- elasticidades.

Entregable: cada score de negocio debe poder expresarse en soles/dólares esperados o en una métrica de utilidad claramente defendible.

## Nivel 3 — Predicción temporal

Dominar:

- validación out-of-time;
- clasificación probabilística;
- calibración;
- Brier score;
- ROC/PR cuando corresponda;
- forecasting probabilístico;
- backtesting;
- drift.

Entregable: probabilidades calibradas y forecasts con intervalos, no solo etiquetas o puntos.

## Nivel 4 — Inferencia causal

Dominar:

- DAGs;
- experimentos aleatorizados;
- ATE / ATT / CATE;
- Difference-in-Differences;
- matching / weighting;
- regression discontinuity;
- instrumental variables;
- event studies;
- uplift / heterogeneous treatment effects.

Entregable: separar “quién probablemente comprará” de “quién comprará gracias a la intervención”.

## Nivel 5 — Optimización y políticas

Dominar:

- programación lineal;
- programación entera;
- restricciones presupuestarias;
- assignment problems;
- policy learning;
- threshold optimization;
- simulación Monte Carlo.

Entregable: una política accionable bajo recursos escasos.

## Nivel 6 — Aprendizaje en producción

Dominar:

- model registry;
- experiment registry;
- decision logs;
- outcomes;
- champion/challenger;
- evaluación de valor realizado;
- retraining triggers;
- gobernanza humana.

Entregable: un sistema que aprende del resultado de sus propias recomendaciones.

## Orden sugerido de proyectos

1. Réplica Redshift → PostgreSQL.
2. Mart de funnel histórico con timestamps confiables.
3. Riesgo de caída predictivo con validación temporal.
4. Registro de acción del supervisor y outcome.
5. Experimento o cuasi-experimento de intervención.
6. CATE/uplift de intervención comercial.
7. Ranking por valor incremental esperado.
8. Forecast de absorción y probabilidad de meta.
9. Pricing causal / elasticidad.
10. Optimizador de precio o asignación sujeto a restricciones.

## Preguntas que deben aparecer siempre en tus diseños

- ¿Cuál es la decisión exacta?
- ¿Quién la toma?
- ¿Cuándo la toma?
- ¿Qué información existe en ese momento?
- ¿Qué acciones son realmente posibles?
- ¿Qué outcome queremos cambiar?
- ¿Cuál es el contrafactual?
- ¿Cuál es el costo de equivocarnos?
- ¿Cuál es el valor económico de acertar?
- ¿Qué restricción limita la acción?
- ¿Cómo sabremos después si funcionó?
