# Medallio: calidad de datos y ruta de modelos

## Propósito

Esta capa permite auditar si los datasets están preparados para entrenar y
evaluar. Conserva los controles de rendimiento predictivo existentes como una
decisión separada: un resultado de calidad `PASS` no dice que el modelo sea
preciso, rentable o listo para producción.

La ejecución lee vistas del PostgreSQL local y guarda solo conteos, ventanas de
fecha, hashes de contratos y resultados agregados. No copia filas fuente,
clientes ni información inmobiliaria a Supabase. No genera predicciones ni
modifica tablas de ventas o forecasts.

## Diagnóstico verificable del gate predictivo

El estado descrito por el usuario reporta cobertura 100%, WAPE N/A, confianza
50%, cero alertas y cero acciones. La cobertura completa confirma que las celdas
previstas están representadas; no confirma que sus outcomes ya se conozcan.

En el diagnóstico del tablero compartido aparecen 84 forecasts emitidos, 70
activos y en incubación, cero evaluados y cero pares maduros. Por eso el gate no
tiene pares `forecast → actual` aptos para calcular WAPE y lo deja como N/A. El
backtest histórico etiquetado `BACKTEST_ONLY` es exploratorio; no sustituye los
outcomes prospectivos congelados. La cifra de Trust no se recalcula aquí: para
explicar su fórmula exacta hace falta revisar `board_summary.json` y el cálculo
que lo produce.

La evidencia necesaria para abrir medición comparativa es:

1. Outcome real completo para un forecast prospectivo, enlazado por proyecto,
   periodo objetivo y horizonte.
2. Registro de maduración que identifique el primer resultado elegible y
   compatible con el stock emitido.
3. Forecast y benchmark ingenuo calculados para la misma población madura.
4. Trazabilidad a run, versión de modelo y corte de datos; cobertura y
   alineación temporal sin excepciones bloqueantes.
5. Soporte por proyecto y horizonte suficiente según los mínimos del gate
   predictivo existente.

No se crean outcomes ni se estima WAPE con celdas incubando. Un WAPE disponible
tampoco sería por sí solo una autorización para operar o una prueba de mayor
rentabilidad.

## Tablas y métricas que se deben revisar

| Pregunta | Relación | Métricas clave |
| --- | --- | --- |
| ¿Qué datos faltan para comparar forecast con realidad? | `analytics.v_forecast_predictive_gate_v283`, `analytics.v_predictive_pre_maturity_readiness_v284` | `mature_pairs`, `global_wape_pct`, `gate_status`, `active_forecast_cells`, `incubating`, `evaluated`, `benchmark_coverage_pct`, `horizon_alignment_pct` |
| ¿Qué forecasts siguen incubando o tienen defectos? | `analytics.v_forecast_issue_quality_v284`, `analytics.v_forecast_maturity_clock_v283`, `model_control.forecast_issue_registry`, `model_control.forecast_naive_benchmark_snapshot` | `maturity_status`, `expected_maturity_date`, `pre_maturity_quality_status`, run/version/cutoff, benchmark primario, pares por proyecto × horizonte |
| ¿El modelo de caída a 30 días usa outcomes maduros y features disponibles al corte? | `features.v_separation_fall_training_30d_health`, `features.v_separation_fall_training_30d_audit`, `features.separation_fall_training_30d`, `features.v_separation_fall_training_30d_regime_profile` | snapshots y lifecycles por clase, censura, ventana de 30 días, duplicados lifecycle × snapshot, exclusiones, soporte por clase y columnas de feature |
| ¿Ventas mensuales son consistentes y evaluables? | `analytics.comercial_proyecto_mes`, `analytics.comercial_unidad_mes`, `analytics.v_comercial_composicion_mes` | grano proyecto × mes, `stock_inicial`, `ventas_mes`, `stock_final`, meses completos/parciales y unidades marcadas para revisión |
| ¿Qué dejó la fiscalización más reciente? | `model_control.v_model_data_quality_latest_gate`, `model_control.v_model_data_quality_latest_results`, `model_control.training_dataset_manifest` | estado de cada suite, pruebas ejecutadas/bloqueadas, excepciones, ventana, grano, target, hash de contrato y firma agregada |

Las vistas `model_control.v_model_data_quality_*` son la nueva capa de
fiscalización. No reemplazan las tablas de evidencia de forecast, los resultados
canónicos de ventas ni los contratos de Decision Engine.

## Suites instaladas

| Suite | Bloquea ante | Avisa ante |
| --- | --- | --- |
| Forecast comercial | Vistas faltantes, ausencia de población activa, predicción negativa, horizonte desalineado, benchmark primario bajo 90%, falta de trazabilidad | Predicción mayor que stock; WAPE aún sin pares maduros |
| Riesgo de caída de separación | Vistas faltantes, entrenamiento vacío, outcome conocido al snapshot, grano duplicado o columnas fuera de allowlist | Menos de 30 lifecycles por clase o proformas sin evidencia temporal suficiente |
| Ventas por proyecto × mes | Panel ausente, ningún mes completo, llaves repetidas o reconciliación de stock/ventas inválida | Mes parcial presente o unidades en revisión; la evaluación debe mostrar sensibilidad para esos casos |

El límite de 30 lifecycles por clase es una alarma inicial de soporte, no una
garantía estadística. Se debe revisar por separado la regla de partición por
lifecycle y el holdout fuera de tiempo antes de comparar candidatos.

### Comprobación de que existe código para entrenar

La suite `model_code_readiness` revisa presencia y sintaxis de módulos y tests.
El repositorio ya tiene el benchmark supervisado de riesgo a 30 días en
`scripts/benchmark_separation_fall_30d.py`, con regresión logística, Random
Forest e HistGradientBoosting, baselines de prevalencia y split temporal que
elimina del train los lifecycles presentes en test. Su prueba de contrato vive
en `decision_engine/tests/test_30d_ml_benchmark_contract.py`. La suite confirma
ese código, el forecast comercial, lead scoring y las pruebas de los datasets
econométricos. Su `PASS` es evidencia de que el camino de código existe; no
ejecuta los trainers con la data actual ni promueve un modelo.

En el view de riesgo, el esquema permite identifiers como metadatos. El
benchmark usa como predictores numéricos `days_since_separation`,
`proforma_age_days_at_snapshot`, `proforma_age_days_at_separation`,
`snapshot_iso_weekday` y `snapshot_month`; y como categóricos
`codigo_proyecto` y `tipo_unidad_principal`. `asesor` es opt-in y no forma parte
de la corrida por defecto. Documento, unidad, proforma, outcome y campos
post-outcome quedan fuera de los predictores. Las interacciones comerciales
siguen sin certificación histórica.

La suite de código se ejecuta junto con las demás o sola:

```powershell
python scripts\model_data_quality_gates.py run --suite model_code_readiness
```

## Abanico de modelos por decisión económica

| Decisión | Objetivo que se puede medir | Candidatos escalonados | Evidencia adicional antes de usar |
| --- | --- | --- | --- |
| Ventas y absorción | Unidades vendidas por proyecto y mes; forecast por horizonte | Naive/mean3 y seasonal naive; ETS/SARIMAX si hay historia suficiente; regresión global o gradient boosting con paneles comparables; reconciliación jerárquica por proyecto | Outcomes mensuales completos, población y horizonte estables, benchmark sobre las mismas celdas; meses parciales fuera del score |
| Tiempo hasta venta | Tiempo a venta con censura de unidades aún disponibles | Curvas Kaplan–Meier como referencia; Cox o hazard discreto; survival forest como challenger | Fecha de entrada/salida verificable y corte temporal por unidad; no tratar unidades vigentes como ventas fallidas |
| Caída de separación | Riesgo de caer antes de conversión en un horizonte explícito | Regresión logística regularizada como baseline; gradient boosting como challenger; calibración por proyecto/horizonte | Snapshots point-in-time, target elegible, split agrupado por lifecycle y fuera de tiempo; interacciones comerciales solo con contrato histórico certificado |
| Precio y composición | Precio de lista observado por m² o mezcla de unidades | Baseline estratificado; regresión hedónica/regularizada; modelos jerárquicos o cuantílicos si existe soporte | Separar precio de lista de precio transado, moneda y tipología; observaciones históricas reales por fecha |
| Leads y canales | Conversión o tiempo a conversión por lead/canal | Regresión logística, hazard y ranking; luego uplift/CATE para acciones de marketing | IDs y eventos de interacción históricos; tratamiento/control o experimento para uplift causal |
| Acciones de venta | Margen esperado neto y tiempo de venta bajo una acción | Primero reglas transparentes y score de priorización; luego optimización restringida sobre efectos medidos | Precio/costo/comisión/margen real, capacidad del equipo, registro de acción y resultado; experimento antes de atribuir causalidad |

Deep learning se considerará si la cantidad de proyectos, ventanas temporales y
resultados maduros supera claramente a las referencias simples y aporta una
mejora fuera de tiempo. La selección parte de las decisiones con más valor
económico medible, no del algoritmo más complejo.

## Secuencia de aprobación

1. **Contrato y calidad:** ejecutar las suites y resolver los bloqueos.
2. **Dataset reproducible:** conservar grano, target, corte, ventana, exclusiones
   y huella del contrato en el manifiesto.
3. **Evaluación temporal:** comparar candidatos contra baselines en la misma
   población y reservar holdout fuera de tiempo.
4. **Decisión económica:** medir margen neto y velocidad; usar experimentos para
   atribuir efectos a una acción comercial.
5. **Operación:** monitorizar deriva y resultados nuevos. No promover modelos de
   forma automática.

## Ejecución desde el PC local

Los comandos siguientes asumen PowerShell, el repo existente en
`C:\projects\bd_replica_crm` y PostgreSQL local ya configurado por
`replica_cygnus.settings`. El worktree adicional mantiene intactos cambios no
confirmados en la carpeta actual.

```powershell
Set-Location C:\projects\bd_replica_crm
git status --short
git fetch origin
git worktree add -b feat/model-data-quality-gates `
  ..\bd_replica_crm-model-quality origin/feat/model-data-quality-gates
Set-Location ..\bd_replica_crm-model-quality
```

Activa el entorno virtual usado por el proyecto. Si el paquete todavía no está
instalado en ese entorno:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Aplica solo el contrato de fiscalización en la PostgreSQL local y corre las
pruebas unitarias:

```powershell
python scripts\schema_sync.py --only model_data_quality_gates
python -m unittest discover -s tests -p "test_model_data_quality_gates.py" -v
```

La prueba de integración es opcional y necesita una base PostgreSQL desechable
para tests. No uses la base de operación. `ABSORCION_TEST_DSN` debe apuntar a
esa base local; el fixture revierte la transacción al terminar:

```powershell
$env:ABSORCION_TEST_DSN = "postgresql://usuario:clave@localhost:5432/medallio_quality_test"
python -m pytest tests\integration\test_model_data_quality_gates_postgres.py -q
Remove-Item Env:ABSORCION_TEST_DSN
```

Ejecuta las cuatro suites, revisa el detalle y vuelve a consultar el último estado:

```powershell
python scripts\model_data_quality_gates.py run
python scripts\model_data_quality_gates.py status
```

Para repetir una sola suite:

```powershell
python scripts\model_data_quality_gates.py run --suite commercial_forecast
python scripts\model_data_quality_gates.py run --suite separation_fall_risk
python scripts\model_data_quality_gates.py run --suite project_month_sales
python scripts\model_data_quality_gates.py run --suite model_code_readiness
```

`run` solo inserta filas agregadas en `model_control.data_quality_*` y un
manifiesto sin datos fuente. Es repetible. Si falta una vista, el resultado
queda `BLOCK`/`BLOCKED` y especifica la relación faltante; el runner no ejecuta
`schema_sync` de los datasets base ni inicia cargas externas. La corrida de
calidad puede confirmar el estado de datos; WAPE cambia de N/A cuando existan
outcomes prospectivos completos y el gate de maduración existente los vincule.

Para inspección SQL local:

```sql
SELECT * FROM model_control.v_model_data_quality_latest_gate ORDER BY suite_key;
SELECT * FROM model_control.v_model_data_quality_latest_results ORDER BY suite_key, test_id;
SELECT * FROM model_control.training_dataset_manifest ORDER BY created_at DESC;
SELECT * FROM analytics.v_forecast_predictive_gate_v283;
SELECT * FROM analytics.v_predictive_pre_maturity_readiness_v284;
```

