# Roadmap 90 días

## Días 1–15 — Instrumentación y contratos

- Congelar definiciones canónicas de separación, venta, caída, stock y absorción.
- Crear `decision_control` y `decision_feedback`.
- Implementar bloqueos por calidad/reconciliación.
- Crear snapshots point-in-time para features.
- Construir baseline D1: riesgo de caída de separaciones.
- Construir baseline D2: cola diaria de leads.

**Salida:** primeras recomendaciones explicables y trazables sin ML complejo.

## Días 16–30 — Riesgo y velocidad comercial

- Backtest temporal de D1/D2.
- Feature set de lead, interacción, proyecto, asesor y separación.
- D3 stock envejecido.
- D4 alertas de desviación de absorción.
- D5 forecast probabilístico de meta mensual.
- Primer endpoint read-only de recomendaciones.

**Gate:** ningún modelo avanza si no supera baseline en métrica económica o de operación.

## Días 31–45 — Modelos v1

- Survival/classification para caída y conversión.
- Calibración de probabilidades.
- Explicabilidad por recomendación.
- Validación por cohortes temporales y proyecto.
- Monitoreo de drift de features y performance.

## Días 46–60 — Matching y recomendación

- D6 lead x asesor con restricciones de capacidad.
- D7 lead x proyecto/unidad con ranking.
- D11 probabilidad de minuta próxima.
- D15 leads recuperables.
- Captura explícita de aceptación/rechazo humano.

## Días 61–75 — Economía de decisión

- Definir función de utilidad esperada.
- Integrar margen, descuento, costo de contacto, CAC y costo de inventario.
- Primer simulador de decisión `what-if`.
- Diseño experimental para marketing/pricing donde sea posible.

## Días 76–90 — Causalidad y optimización controlada

- D8/D16 prototipo de pricing, inicialmente shadow mode.
- D9/D13 marco de incrementality de marketing.
- Policy evaluation del historial de recomendaciones.
- Dashboard de decisiones: valor sugerido, aceptado y realizado.
- Checklist de extracción a repositorio independiente.

## North Star del sistema

No es cantidad de modelos. Es:

`valor económico incremental realizado por decisiones asistidas / periodo`

Métricas secundarias:

- uplift de conversión;
- reducción de caídas;
- reducción de días de inventario;
- margen protegido;
- precisión/calibración de riesgo;
- tasa de adopción de recomendaciones;
- porcentaje de recomendaciones con resultado observable.
