# MEDALLIO — Estudio de Pricing Inmobiliario

## Objetivo

Convertir el pricing inmobiliario en un ciclo reproducible de decisión:

`dato → evidencia → diagnóstico → escenario → recomendación → aprobación → acción → outcome → aprendizaje`

El output ejecutivo está inspirado en un one-pager de pricing bancario, pero adaptado a inventario inmobiliario. El reporte no se limita a mostrar precios: debe explicar **qué está pasando, por qué importa, qué alternativas existen y qué acción conviene revisar**.

## North Star

**Valor económico realizado por decisiones de pricing, sujeto a absorción, coherencia comercial y evidencia.**

No se optimiza accuracy. No se optimiza precio aislado. Se busca preservar simultáneamente:

- ingreso/margen;
- velocidad de absorción;
- salud del inventario;
- coherencia por tipología, piso y proyecto;
- auditabilidad de la decisión.

## Fuentes Medallio usadas en v1

1. `core.v_unidades_fuentes`
   - código de unidad y proyecto;
   - tipología y `tipologia_ubicacion`;
   - piso y áreas;
   - estado comercial;
   - precio lista / proforma / venta;
   - moneda y provenance.

2. `analytics.fact_absorcion_proyecto_diario`
   - stock inicio/fin;
   - separaciones netas 30d;
   - ventas 30d;
   - absorción neta 30d;
   - tasa de caída;
   - meses de stock.

3. `pricing_analytics.fact_precio_unidad_diario`
   - nuevo histórico diario de precio por unidad;
   - se alimenta con `pricing_analytics.capture_price_snapshot()`;
   - empieza a construir evidencia temporal desde la fecha de instalación.

## Qué agrega esta rama

### Capa SQL

`sql/60_pricing_study/00_pricing_study.sql`

Crea:

- `pricing_analytics.fact_precio_unidad_diario`
- `pricing_analytics.v_pricing_unit_current`
- `pricing_analytics.v_pricing_unit_positioning`
- `pricing_analytics.v_pricing_project_scorecard`
- `pricing_analytics.v_price_change_events`
- `pricing_analytics.capture_price_snapshot()`

### Capa Python

`src/replica_cygnus/pricing_study/service.py`

Produce:

- PDF ejecutivo de 3 páginas;
- PNG del one-pager principal;
- scorecard por proyecto;
- escenarios de stress;
- ranking de unidades a revisar.

### Configuración

`config/pricing_study.yml`

Separa reglas de negocio del código:

- escenarios de variación de precio;
- elasticidad usada solo como supuesto de stress;
- guardrail de absorción;
- corredor interno de precio por m²;
- meses de stock rápido/lento;
- mínimos de evidencia para abrir la etapa de modelado.

## Reporte ejecutivo

### Página 1 — Comité / CEO

Replica la lógica comunicacional del caso bancario:

**Contexto → Problema → Objetivo → Enfoque**

Luego:

**Analizar → Segmentar → Simular → Recomendar**

Incluye:

- valor de stock disponible;
- absorción neta 30d;
- meses de stock;
- precio mediano por m²;
- gráfico precio m² vs absorción;
- ranking de meses de stock;
- stress test de precio;
- insights ejecutivos;
- nivel de evidencia acumulada.

### Página 2 — Unidad / Pricing Squad

Incluye:

- índice de precio de cada unidad contra su benchmark interno;
- corredor de referencia;
- unidades candidatas a revisar descuento;
- unidades candidatas a testear subida;
- tabla priorizada por unidad.

Las acciones son **candidatos de revisión**, no cambios automáticos.

### Página 3 — Metodología / Auditoría

Explica:

- lineage del dato;
- diferencias entre descriptivo, stress test y causalidad;
- gates mínimos para modelado;
- guardrails de gobierno;
- cierre del feedback loop.

## Modos analíticos

### 1. Diagnóstico actual — disponible desde v1

Usa el precio vigente, precio por m², posición relativa, stock y absorción.

### 2. Stress test — disponible desde v1

Simula variaciones configurables de precio. La elasticidad de `config/pricing_study.yml` es un **supuesto de planeamiento** y el PDF lo etiqueta explícitamente como no causal.

### 3. Elasticidad observada — siguiente gate

Solo debe abrirse cuando exista variación histórica real de precios y suficiente longitud temporal.

El simple hecho de tener 60 días o 20 cambios de precio no demuestra causalidad; solo indica que existe material suficiente para comenzar una revisión econométrica.

### 4. Elasticidad causal / experimentación — fase posterior

Requiere identificación defendible, por ejemplo:

- cambios de precio escalonados;
- grupos comparables;
- experimentos o cuasi-experimentos;
- controles por tendencia, proyecto, tipología y shocks comerciales;
- registro de promociones y campañas simultáneas.

## Ciclo completo por squads / corrientes

### Stream A — Data Foundation

Responsabilidad:

- snapshots de precio;
- calidad y provenance;
- precio efectivo y moneda;
- historia de estado comercial;
- reconciliación con venta observada.

Gate de salida: pricing histórico reproducible.

### Stream B — Pricing Economics

Responsabilidad:

- corredores de precio;
- dispersión por tipología/piso;
- precio lista vs vendido;
- absorción y meses de stock;
- métricas de valor económico.

Gate de salida: diagnóstico interpretable y accionable.

### Stream C — Modeling

Responsabilidad:

- elasticidad;
- survival / time-to-sale;
- propensity de venta por unidad;
- heterogeneidad por tipología;
- validación temporal.

Gate de salida: challenger que mejora una política baseline.

### Stream D — Simulation & Optimization

Responsabilidad:

- escenarios de precio/descuento;
- restricciones comerciales;
- coherencia vertical;
- target de absorción;
- valor esperado.

Gate de salida: recomendación con trade-off visible.

### Stream E — Executive Reporting

Responsabilidad:

- one-pager de comité;
- anexos por proyecto;
- ranking de acciones;
- trazabilidad de supuestos;
- exportables PDF / PNG / CSV / Power BI.

Gate de salida: un gerente puede decidir sin abrir el notebook.

### Stream F — Decision & Outcome Learning

Responsabilidad:

- recomendación emitida;
- acción efectivamente aprobada;
- precio aplicado;
- fecha efectiva;
- outcome 30/60/90 días;
- valor realizado;
- recalibración.

Gate de salida: demostrar predicción/escenario → acción → resultado observado.

## Estrategia de ramas

Esta entrega vive en:

`feat/pricing-inmobiliario-study-v1`

Siguientes ramas recomendadas, solo después de validar outputs reales:

1. `feat/pricing-elasticity-v2`
   - panel histórico;
   - elasticidad asociativa y validación temporal;
   - comparación contra baseline.

2. `feat/pricing-causal-v3`
   - diseño experimental/cuasi-experimental;
   - estimandos causales;
   - heterogeneidad por proyecto/tipología.

3. `feat/pricing-decision-loop-v4`
   - registro de recomendación/acción/outcome;
   - valor económico realizado;
   - vistas Power BI de aprendizaje.

No conviene crear estas ramas como código productivo antes de comprobar que el snapshot histórico y el one-pager funcionan con datos reales.

## Primera ejecución

Desde la raíz del repositorio:

```bat
python scripts\pricing_study.py --install-sql --capture-snapshot
```

Para un proyecto:

```bat
python scripts\pricing_study.py --project Urbanzen --capture-snapshot
```

Ejemplo Nápoles:

```bat
python scripts\pricing_study.py --project Napoles --capture-snapshot
```

Salidas:

```text
output/pricing_study/
  Pricing_Inmobiliario_<scope>_YYYY_MM_DD.pdf
  Pricing_Inmobiliario_<scope>_YYYY_MM_DD_executive.png
  Pricing_Inmobiliario_<scope>_YYYY_MM_DD_scorecard.csv
  Pricing_Inmobiliario_<scope>_YYYY_MM_DD_scenarios.csv
  Pricing_Inmobiliario_<scope>_YYYY_MM_DD_unit_actions.csv
```

## Operación diaria sugerida

Después de validar la primera ejecución, agregar **solo** la captura de snapshot al pipeline horario/diario. Para pricing basta un snapshot diario si los precios no cambian intradía de forma relevante.

Comando:

```bat
python scripts\pricing_study.py --capture-snapshot
```

Si no se necesita generar el PDF cada día, conviene separar posteriormente `capture_price_snapshot` de `generate_pricing_study` en dos jobs: captura diaria y reporte bajo demanda/semanal.

## Reglas que no deben romperse

- `raw_cygnus` y `raw_mercado` no se modifican.
- El benchmark de `v_pricing_unit_positioning` es interno; no debe llamarse "precio de mercado".
- Un stress test no debe comunicarse como elasticidad estimada.
- Ningún cambio de precio se ejecuta automáticamente desde este módulo.
- Toda recomendación futura debe preservar el precio anterior, el supuesto/modelo, la aprobación y el outcome.
- Si el dato de absorción está incompleto o desactualizado, el reporte debe considerarse diagnóstico parcial, no recomendación definitiva.
