# Forecasting Cygnus: revisión de unidades y tablero Power BI

La cobertura del último run indica qué proyectos quedaron fuera del pronóstico
por incidencias pendientes y cuánto stock representan. La investigación se hace
a nivel de unidad, conservando los runs emitidos para comparación.

## Resolver las incidencias de la fuente

`unidades_revision` de `v_absorcion_ventas_mensual` cuenta las mismas unidades
actuales en **cada mes**. En el panel aportado cada uno de NP, SL y TZ marca una
unidad a lo largo de todos sus meses: contar filas mensuales no da el número de
unidades distintas. Si cambió el origen de datos desde esa captura, volver a
contar en la vista de unidades antes de actuar.

Desde VS Code, en la carpeta `bd_replica_crm_forecasting` actualizada, obtener
las unidades y proformas sin cambiar la base:

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py review
```

El comando consulta la evidencia **actual** de NP, SL y TZ; se puede repetir con
`--project NP --project SL --project TZ`. `distinct_review_units` debe indicar
cuántas unidades siguen pendientes. Compartir el JSON devuelto permite decidir
qué registro/documento requiere intervención sin publicar datos personales.

Como alternativa en un editor SQL, ejecutar las tres consultas de
[`02_review_diagnostics.sql`](../sql/97_commercial_forecasting/02_review_diagnostics.sql)
en el PostgreSQL **local** `medallio_dw`, en este orden. La primera dimensiona
stock y unidades; la segunda identifica unidad, estado, duplicidad de ventas,
ciclos pendientes y venta sin fecha; la tercera muestra proformas, fechas y
observaciones de sus ciclos. Son consultas de lectura que no exponen PII.

Para cada unidad, contrastar el motivo con su proforma, fecha_de_minuta,
proceso Venta y Anulación en la réplica local, conforme a las reglas ratificadas
en [Absorción mensual](ABSORCION_VENTAS_MENSUAL.md):

| Evidencia observada | Resolución requerida |
|---|---|
| Más de una venta vigente elegible | Identificar cuál proforma fue anulada o cuál ciclo corresponde a la unidad, y corregir el registro fuente/documental. No escoger una fecha arbitraria. |
| Ciclo pendiente o fecha de pago inválida | Corregir o documentar en el sistema de origen el pago, proforma, unidad o fecha; respetar la prohibición del respaldo Venta para 2026. |
| Estado actual vendido sin venta fechada | Conciliar el estado con la evidencia documental. No convertir el estado actual en una fecha histórica inventada. |

Después de que el refresh habitual sincronice la corrección y se actualice la
capa de absorción, repetir las consultas y verificar que las tres unidades
resueltas ya no estén en `v_absorcion_ventas_revision`. Emitir **otro** run con
`scripts/64_forecasting_medallio.bat`, revisar su nueva cobertura y conservar
intacto el run anterior. La vista de cobertura corresponde al último run; no
se actualiza retrospectivamente al cambiar la vista de absorción.

## Conectar Power BI Desktop

Usar `pPostgresServer` y `pPostgresDatabase` (`medallio_dw`) del modelo existente.
En Power Query, crear una **consulta en blanco** por cada archivo M, abrir Editor
avanzado y pegar su contenido. Nombrar las consultas como el archivo sin `.m`:

| Archivo en `powerbi/M/` | Grano y uso |
|---|---|
| `qForecastReviewQueue.m` | Una unidad con revisión, estado y evidencias de ciclo. Fuente viva. |
| `qForecastCoverage.m` | Un proyecto del último run; stock cubierto o en cuarentena. |
| `qForecastCurrent.m` | Una predicción seleccionada por proyecto y horizonte, último run. |
| `qForecastCandidateStatus.m` | Disponibilidad y selección de cada modelo en el último run. |
| `qForecastAsIssued.m` | Una predicción seleccionada **por run/proyecto/horizonte**, con el primer resultado maduro congelado si existe. Historial. |

Crear las dos tablas calculadas y medidas de
[`05_Forecasting_Cygnus.dax`](../powerbi/DAX/05_Forecasting_Cygnus.dax).
Relacionar `DimForecastProject[project]` (lado uno) con `project` de las cuatro
tablas de proyecto; relacionar `DimForecastHorizon[horizon]` con `horizon` de
`qForecastCurrent` y `qForecastAsIssued`. Usar filtros de dirección única desde
las dimensiones. `qForecastCandidateStatus` queda como tabla descriptiva sin
relación por proyecto. No relacionar coverage con horizonte: sus 17 filas
representan el inventario del run, no seis copias del stock.

Armar una página **Cobertura y pronóstico** con:

1. Tarjetas: stock total, stock cubierto, cobertura %, stock en cuarentena y
   unidades pendientes distintas. Ordenar el trabajo por stock excluido.
2. Barras por proyecto de stock (cobertura) y una matriz de unidad/motivo
   (`qForecastReviewQueue`) para el equipo que resuelve la evidencia.
3. Segmentador de un solo valor `DimForecastHorizon[horizon]`; barras de
   `Pronóstico acumulado seleccionado`, meta y brecha por proyecto. Horizontes
   1, 3 y 6 son acumulativos: **no sumar horizontes**.
4. Tabla de modelos con `model`, `projects_with_candidate`,
   `selected_projects`, `pooled_training_rows` (solo GMM/RF) y
   `accepted_validation_projects`.
   Disponibilidad del bosque/GMM acredita entrenamiento y propuesta; selección
   cero significa que no superaron el control de validación. No mostrar su
   importancia de variables como causalidad.

Armar otra página **Pronóstico emitido vs resultado** con segmentadores de
`run_id` y horizonte único, y:

1. Tabla `run_id`, `origin`, `project`, `horizon`, `created_at_lima`,
   `prediction`, `actual`, `eligibility_reason`, `issued_before_window_start`
   y `eligible_for_operational_scoring` de `qForecastAsIssued`.
2. Tarjetas `Resultados comparables`, `MAE emitido`, `Sesgo emitido`,
   `WAPE emitido` y `Cobertura observada 80%`. Deben quedar vacías si no hay
   resultados compatibles; cero es un error medido, no falta de evidencia.
3. Serie por run emitido que muestre error y sesgo cuando maduren horizontes.
   `eligible_for_strict_prospective_scoring` es más exigente que la métrica de
   emisión antes del cierre. Mostrar ambas poblaciones por separado.

Si el run aún no tiene resultados maduros, las tarjetas de error estarán vacías.
La bandera `issued_before_window_start` permite identificar una emisión que
ocurrió después del inicio de la ventana. Las métricas retrospectivas de
`backtest.csv` son diagnóstico, no deben
unirse en esta página como si fueran resultados emitidos antes de suceder.

Al presentar el sistema: se entrenaron modelos, se emitieron alternativas,
la política seleccionó `mean3` ante evidencia temporal insuficiente y las
predicciones quedaron versionadas para medirlas cuando maduren. Una mejora
comercial atribuible a ML requerirá comparar decisiones y resultados futuros
con una referencia y acciones registradas; una tabla de pronósticos por sí sola
no demuestra causalidad ni impacto económico.
