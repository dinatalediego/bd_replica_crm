# Medallio Ambassador v2.6 — Economic Decision Layer

## La pregunta que responde

La v2.6 no pregunta solamente:

> ¿Qué sabe Medallio?

Pregunta:

> **¿Qué altura de desafío de negocio está resolviendo Medallio y cuánto valor económico puede mover?**

## Marco de Growth Altitude

| Nivel | Desafío | Pregunta |
|---|---|---|
| L1 | Visibilidad & Reporting | ¿Qué pasó? |
| L2 | Diagnóstico & Comparabilidad | ¿Por qué pasó? |
| L3 | Predicción & Forward View | ¿Qué probablemente pasará? |
| L4 | Decision Intelligence | ¿Qué deberíamos hacer? |
| L5 | Optimización Económica | ¿Cuánto valor está en juego? |
| L6 | Aprendizaje Causal | ¿La acción realmente generó mejora? |
| L7 | Closed-loop Growth OS | ¿Cómo aprende y reasigna capital el sistema? |

Importante: **altura ≠ sofisticación técnica**.

Un modelo complejo que no cambia una decisión de negocio puede estar en L3.
Una regla sencilla con causalidad, ROI y aprendizaje puede estar más arriba.

## Desafíos de crecimiento que monitorea

- Crecimiento de ingresos
- Demanda & conversión
- Pricing & descuentos
- Stock & velocidad
- Forecast & planeamiento
- Ejecución comercial
- Aprendizaje & gobierno

Cada desafío recibe su propia altura.

## Economic Decision Queue

Ambassador busca evidencia económica real en CSV/XLSX de la corrida.

Campos que intenta detectar:

- meta / target
- ventas monetarias / revenue
- gap / brecha
- valor de stock / monto por vender
- impacto / benefit / value_to_capture
- costo de acción
- uplift %
- confidence
- ROI

Cuando existen, calcula de forma conservadora:

### Value at Risk
Brecha económica identificada.

### Economic Exposure
Capital / stock expuesto; **no se llama automáticamente riesgo**.

### Value to Capture
Beneficio incremental explícito o escenario derivado de gap × uplift cuando ambos existen.

### Confidence-adjusted Value
`Value to Capture × confidence`

### Expected ROI
Sólo si existe ROI explícito o `value_to_capture` + `action_cost`.

## Anti-hallucination económica

Si no existe evidencia para cuantificar una decisión:

```text
quantification_status = unquantified
```

Medallio no inventa montos.

La slide y el registro indican qué evidencia falta:

- value_at_risk
- value_to_capture
- action_cost
- measured_confidence
- expected_roi
- realized_outcome

## Nuevos artifacts

En:

```text
artifacts\medallio_ceo_briefing\
```

se generan:

```text
economic_decision_register.csv
business_challenge_altitude.csv
economic_decision_summary.json
```

## Google Sheets

El Executive Register incorpora dos pestañas nuevas:

```text
ECONOMIC_DECISIONS
CHALLENGES
```

## Nuevo deck

Morning / Evening genera 8 slides:

1. Executive Growth & Economic Board
2. Altura de los desafíos
3. Mapa de desafíos de crecimiento
4. Economic Decision Queue
5. Portafolio de proyectos
6. Recomendaciones por frente
7. Narrativa Dirección vs disciplina interna
8. Rigor económico / evidencia faltante

## Disciplina económica

La v2.6 distingue:

```text
Value at Risk
≠
Value to Capture
≠
Confidence-adjusted Value
≠
Realized Outcome
```

Eso evita presentar escenarios como si fueran beneficios realizados.

## Idempotencia de Slides

v2.6 también mejora la operación:
- elimina el slide inicial vacío en decks nuevos;
- reemplaza las slides del mismo slot si vuelves a ejecutar Morning/Evening;
- evita multiplicar versiones idénticas por reintentos.

## Instalación

Reemplaza:

```text
scripts\medallio_ambassador_v2.py
```

No necesitas cambiar tu config actual: el script tiene defaults seguros.

Opcionalmente copia el contenido de:

```text
config\v2_6_economic_policy_fragment.json
```

a tu `medallio_ambassador_v2.json`.

## Prueba

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Debes ver una línea similar a:

```text
ECONOMIC | altitude=L4 Decision Intelligence | risk=N/Q | capture=N/Q | quantified=0
```

Eso **no es un error**. Significa que Medallio ya decide, pero todavía no tiene
evidencia monetaria suficiente para llamar esas decisiones "económicas".

Luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Qué significa el salto L4 → L5

Éste es el desafío central de la v2.6.

L4:
> "Deberíamos cambiar pricing en este proyecto."

L5:
> "Cambiar pricing en este proyecto tiene S/ X de Value at Risk,
> S/ Y de Value to Capture, costo S/ Z, confianza C y ROI esperado R."

L6:
> "Lo hicimos y el uplift incremental causal fue U."

L7:
> "Medallio aprendió del outcome y cambió automáticamente la siguiente recomendación."

Ésa es la altura que queremos que Medallio alcance para convertirse en una
verdadera fábrica de crecimiento, no solamente una fábrica de reportes.
