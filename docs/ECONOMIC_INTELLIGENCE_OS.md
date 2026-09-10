# Medallio Economic Intelligence OS

Sistema cerrado de analytics, econometría y machine learning para transformar historia de stock inmobiliario en evidencia, forecast, decisiones y aprendizaje.

## North Star

Responder de forma gobernada:

1. ¿cuánto stock completo existe hoy?
2. ¿qué parte del stock histórico observamos realmente en el ledger?
3. ¿cuánto se absorbió mes a mes y acumulado?
4. ¿cuántos departamentos absorberemos / venderemos en los próximos N meses?
5. ¿cuándo se agotará el stock a distintos escenarios?
6. ¿qué factores micro y macro explican/predicen la dinámica?
7. ¿qué decisión comercial se propone, con qué guardrail y cómo mediremos el resultado?

## Contrato crítico de stock

No se reemplaza `stock_inicio_observado` por el universo actual completo.

Se mantienen dos conceptos:

- `stock_total_departamentos_actual_ref`: conteo completo ACTUAL de departamentos en `core.dim_unidad`. Es una referencia estructural; no prueba que todas esas unidades estuvieron disponibles desde el inicio comercial.
- `stock_ofertado_observado_acum`: `stock_inicial_observado_ledger + altas_acumuladas_ledger`. Es la oferta cuya entrada sí tiene evidencia histórica en el ledger.

La diferencia entre ambas se interpreta como **gap de cobertura histórica**, no automáticamente como error ni como stock faltante.

### Altas acumuladas

`ALTAS ACUMULADAS LEDGER` suma `ALTA_STOCK` y **no resta caídas**.

Una caída comercial reingresa una unidad al stock, pero no crea una unidad nueva. Por eso restar caídas de las altas destruiría la semántica de oferta introducida.

## North Star predictiva

Para agotamiento de stock:

```text
demanda_neta_stock = separaciones efectivas - caídas efectivas
```

Una minuta no vuelve a sacar la unidad de stock disponible: esa salida ocurrió al separar. Por ello el sistema predice en paralelo:

- demanda neta futura → stockout;
- ventas/minutas futuras → conversión comercial.

Targets soportados:

- `target_mov_neto_next_1m/3m/6m/...`
- `target_minutas_next_1m/3m/6m/...`

## Corrientes / squads

| Squad | Pregunta | Productos | Cadencia |
|---|---|---|---|
| Data Foundation & Governance | ¿puedo confiar en el dato? | contratos, coverage, DQ, provenance | diaria/mensual |
| Analytics & BI | ¿qué pasó? | matrices, cohortes, stock/flujo, acumulados | semanal/mensual |
| Microeconomics | ¿qué mueve un proyecto/unidad? | escasez, mix, precio, caídas, conversiones | semanal |
| Macroeconomics | ¿qué mueve el portafolio/mercado? | oferta/demanda agregada, tasas, TC, ciclo | mensual |
| Forecasting & ML | ¿qué pasará? | demanda N meses, minutas, stockout | mensual |
| Revenue / Pricing | ¿qué palanca mover? | escenarios, elasticidad cuando exista evidencia, guardrails | quincenal |
| Experimentation / Causal | ¿qué causó qué? | A/B, rollout, diff-in-diff, uplift | por experimento |
| Decision Intelligence / PMO | ¿qué decidimos y aprendimos? | comité, action register, outcome review | semanal/mensual |
| MLOps / Model Governance | ¿sigue funcionando? | champion/challenger, drift, model card | mensual |

## Feature mart

`analytics.v_econ_project_monthly_features`

Combina:

### Historia segura para ML

- stock inicio/final observado;
- altas, separaciones, caídas, movimiento neto, minutas;
- lags y medias móviles;
- edad comercial;
- estacionalidad sin/cos;
- agregados endógenos del portafolio.

### Macro externo opcional

`analytics.econ_macro_monthly`

- tasa de referencia BCRP;
- tasa hipotecaria;
- PEN/USD;
- inflación;
- actividad;
- desempleo.

La tabla puede estar vacía: el sistema no inventa macroeconomía.

### Referencias actuales — excluidas del entrenamiento histórico por defecto

- stock total actual del proyecto;
- precio lista actual;
- precio/m² actual;
- descuento actual;
- cobertura ledger vs universo actual.

Estas variables son útiles para diagnóstico y escenarios, pero pueden generar leakage si se usan como si hubieran sido conocidas históricamente.

## Modelos challenger

### Demanda neta / absorción

- Ridge;
- HistGradientBoostingRegressor;
- RandomForestRegressor.

### Minutas

Además:

- PoissonRegressor.

La promoción se decide por holdout temporal reciente, no por fit in-sample.

Métricas:

- MAE;
- RMSE;
- SMAPE;
- error por proyecto/etapa.

## Econometría

Se incluyen modelos interpretables con:

- efectos fijos por proyecto;
- lags;
- estacionalidad;
- exposición de stock para conteos;
- errores robustos.

No se etiqueta una asociación como causal sin una estrategia de identificación.

## Gradientes y clusters

### Regímenes latentes

PCA + KMeans para encontrar estados proyecto-mes como lanzamiento, aceleración, madurez o stock lento. Son segmentos descriptivos, no causas.

### Gradiente predictivo

Diferencia finita:

```text
∂ŷ/∂x ≈ [f(x+ε) - f(x-ε)] / 2ε
```

Traduce un modelo no lineal a sensibilidad ejecutiva. No es elasticidad causal.

## Pricing y curvas de indiferencia

Sin historial de precio o elección individual, no se fabrica una curva de utilidad.

Se permiten:

- curvas iso-presupuesto como proxy visual;
- escenarios de precio con supuestos explícitos;
- elasticidad causal sólo cuando exista snapshot histórico de precio o experimento identificable.

## Notebooks

```text
notebooks/economic_intelligence/
00_contrato_y_auditoria.ipynb
01_puente_matrices_estadistica.ipynb
02_microeconomia_proyecto.ipynb
03_macroeconomia_mercado.ipynb
04_clusters_gradientes_regimenes.ipynb
05_forecast_demanda_y_agotamiento.ipynb
06_econometria_champion_challenger.ipynb
07_escenarios_oferta_demanda_pricing.ipynb
08_comite_ceo_pmo.ipynb
09_experimentacion_mlops_decision_memory.ipynb
```

## Producto Excel mejorado

```powershell
scripts\63_exportar_absorcion_economica.bat
```

Agrega al reporte de absorción:

- stock total proyecto ref. actual;
- stock inicio observado;
- altas del mes;
- altas acumuladas ledger;
- stock ofertado observado acumulado;
- cobertura ledger;
- absorción mensual y acumulada.

Output:

```text
output/economic_intelligence/Absorcion_Economica_YYYY_MM_DD.xlsx
```

## Secuencia recomendada

1. ejecutar `00_contrato_y_auditoria`;
2. validar identidades y coverage;
3. ejecutar puente/micro/macro;
4. ejecutar clusters para regímenes;
5. backtest del forecast;
6. revisar champion/challenger;
7. simular escenarios;
8. abrir notebook de comité;
9. registrar acción y outcome antes de retraining.

## Gate de producción

No promover un modelo porque "se ve bien".

Debe demostrar:

- contrato de target correcto;
- no leakage;
- holdout temporal;
- error menor que baseline;
- estabilidad por proyecto;
- reglas económicas razonables;
- coverage suficiente;
- model card;
- decisión y outcome medibles.
