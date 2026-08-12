# Versión 0.2.0 — Decision Intelligence Foundation

Extiende la réplica Redshift → PostgreSQL con una arquitectura explícita:

`datos → causalidad → predicción → economía → decisión → aprendizaje`.

Cambios principales:
- contratos de decisión versionados en YAML;
- esquemas `features`, `decision_intelligence`, `model_control`, `experiments`;
- registro de modelos, recomendaciones, acciones y outcomes;
- baseline causal Difference-in-Differences;
- baseline predictivo de clasificación logística;
- baseline de forecast ETS;
- motor de valor económico esperado y restricciones de capacidad;
- feedback loop para evaluar decisiones realizadas;
- tres casos de uso iniciales: riesgo de caída, priorización de leads y pricing.

La v0.2.0 es compatible conceptualmente con la v0.1.0: la capa de réplica se conserva.


## v0.2.2 — Redshift timeout resilience

- Aumenta el timeout de socket Redshift a 300 s por defecto mediante `REDSHIFT_SOCKET_TIMEOUT`.
- Habilita TCP keepalive configurable.
- Usa `SHOW COLUMNS` como mecanismo principal de descubrimiento de columnas y `SVV_COLUMNS` como fallback.
- Añade `scripts/12_diagnosticar_redshift.bat`.
- Mantiene la corrección de índices únicos de v0.2.1.
