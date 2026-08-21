# Commercial Decision Map

Priorización inicial para transformar datos en decisiones. Escala 1–5. `priority_score` pondera impacto económico, frecuencia, factibilidad de datos y riesgo de implementación.

| # | Decisión | Dueño | Grano | Método inicial | Evolución | Impacto | Datos | Riesgo | Prioridad |
|---|---|---|---|---|---|---:|---:|---:|---:|
| 1 | ¿Qué separaciones requieren intervención hoy? | Comercial | separación | reglas por edad/inactividad | survival + clasificación | 5 | 5 | 2 | 4.8 |
| 2 | ¿Qué leads deben trabajarse hoy? | Asesor/Call Center | lead | recency + funnel + actividad | propensity/uplift | 5 | 5 | 2 | 4.8 |
| 3 | ¿Qué unidades están envejeciendo peligrosamente? | Comercial/Pricing | unidad | antigüedad + absorción | survival inventario | 5 | 5 | 2 | 4.7 |
| 4 | ¿Qué proyecto se desvía de su velocidad esperada? | Gerencia | proyecto-día | control estadístico | forecast jerárquico | 5 | 5 | 2 | 4.7 |
| 5 | ¿Llegaremos a la meta mensual? | Gerencia | proyecto/asesor-mes | run-rate | probabilistic forecast | 5 | 4 | 2 | 4.5 |
| 6 | ¿Qué lead asignar a qué asesor? | Supervisión | lead-asesor | reglas de capacidad | matching/uplift | 5 | 4 | 3 | 4.2 |
| 7 | ¿Qué proyecto/unidad mostrar a un lead? | Asesor | lead-unidad | filtros declarados | recommender/ranking | 5 | 3 | 3 | 4.0 |
| 8 | ¿Conviene aplicar descuento a esta unidad? | Pricing/Gerencia | unidad-fecha | matriz de reglas | elasticidad + optimización | 5 | 3 | 4 | 3.9 |
| 9 | ¿Dónde asignar presupuesto de marketing? | Marketing | canal-proyecto | CAC/conversión | incrementality + optimizer | 5 | 3 | 4 | 3.8 |
| 10 | ¿Qué anomalía invalida una decisión? | BI/Data | entidad-regla | QA determinista | anomaly detection | 5 | 5 | 1 | 4.9 |
| 11 | ¿Qué separación tiene mayor probabilidad de minuta esta semana? | Comercial | separación | ventana temporal | survival/hazard | 4 | 5 | 2 | 4.4 |
| 12 | ¿Qué unidades deberían priorizarse en campañas? | Marketing | unidad | stock x velocidad | expected value | 4 | 4 | 2 | 4.2 |
| 13 | ¿Qué canal produce ventas incrementales, no solo atribuidas? | Marketing | canal-periodo | cohortes | causal inference | 5 | 2 | 4 | 3.5 |
| 14 | ¿Qué asesor necesita coaching y en qué etapa? | Supervisión | asesor-etapa | funnel decomposition | hierarchical models | 4 | 4 | 3 | 3.9 |
| 15 | ¿Qué leads abandonados son recuperables? | Call Center | lead | inactividad | propensity/uplift | 4 | 4 | 2 | 4.1 |
| 16 | ¿Qué precio maximiza margen esperado y velocidad? | Pricing | unidad-fecha | comparables internos | elasticity + constrained optimization | 5 | 2 | 5 | 3.4 |
| 17 | ¿Qué proyecto tiene problema de producto vs precio vs ejecución? | Gerencia | proyecto-periodo | decomposition | causal/structural diagnostics | 5 | 3 | 4 | 3.7 |
| 18 | ¿Qué leads tienen fit con tipología/dormitorios/distrito? | Comercial | lead-producto | reglas declarativas | learning-to-rank | 4 | 3 | 3 | 3.7 |
| 19 | ¿Qué inventario debe proteger margen y no descontarse? | Pricing | unidad | velocidad + escasez | opportunity-cost model | 4 | 3 | 3 | 3.7 |
| 20 | ¿Qué acciones recomendadas realmente funcionaron? | Gerencia/Data | recomendación | logging + cohortes | policy evaluation | 5 | 1 | 3 | 3.5 |

## Ola 1 — instrumentar y ganar confianza

- D10 Calidad que bloquea decisiones.
- D1 Riesgo/intervención de separaciones.
- D2 Priorización diaria de leads.
- D3 Riesgo de stock envejecido.
- D4 Desviación de absorción.
- D5 Forecast de meta.

## Ola 2 — asignación y recomendación

- D6 Lead x asesor.
- D7 Lead x unidad/proyecto.
- D11 Minuta próxima.
- D15 Recuperación de leads.

## Ola 3 — causalidad y optimización

- D8/D16 Pricing y descuentos.
- D9/D13 Marketing incremental.
- D17 Diagnóstico causal de proyecto.
- D20 Evaluación de políticas.

## Criterio de aceptación de un caso de uso

Una decisión no se considera productiva hasta que tenga: fuente confiable, instante de decisión definido, baseline, backtest temporal, métrica económica, explicación, mecanismo de feedback y dueño operativo.
