# Arquitectura de forecasting comercial: robustez v2

El objetivo es obtener evidencia comparable y decisiones reproducibles. Un modelo
más complejo puede tener peor error. Esta versión conserva los cuatro candidatos
y hace más exigente la selección y más explícitas sus limitaciones.

## Contratos y responsabilidades

| Capa | Responsabilidad implementada | Evidencia |
|---|---|---|
| Fuente local y versiones | Contrato de conteos/stock, meses cerrados, snapshots append-only; comparar revisiones contra el snapshot anterior | `quality.json`, `snapshot_comparison` |
| Elegibilidad | Cuarentena coherente incluso si el stock terminó en cero; cada proyecto tiene estado y stock cubierto | `project_coverage.csv`, vista de cobertura |
| Entrenamiento | Transformaciones/objetivos limitados al corte; seis meses mínimos por proyecto para ML; GMM descarta componentes con menos de diez filas efectivas | `training_cuts.json`, `model_profiles.json` |
| Selección | Trayectorias completas en validación; controles por proyecto; candidatos comparados sobre la misma población con fallback explícito | `selection_policy.json` |
| Prueba reservada | Aplicar la política congelada en validación, sin usar la prueba para escoger modelos | `policy_backtest.csv`, `paired_comparisons.csv` |
| Incertidumbre y soporte | Contar cortes distintos y no solapados; calibración por horizonte y tamaño de stock; detectar entradas fuera de rango de entrenamiento | `interval_calibration.csv`, `robustness.json`, `model_profiles.json` |
| Reproducibilidad | Versiones de librerías/Python, bytes del código utilizado, hashes de todos los archivos | `source_code/`, `checksums.json` |
| Resultados observados | Primer snapshot completo por proyecto/horizonte, compatibilidad con stock emitido, razón de exclusión, fecha de emisión en Lima | vistas de rendimiento y monitoreo |

`core.py` entrena y genera candidatos. `evaluation.py` decide exclusivamente con
validación y reporta la prueba. `robustness.py` controla cobertura, calibración,
revisiones, compatibilidad e integridad. `service.py` orquesta archivos y PostgreSQL.

## Cómo se decide el modelo

Se usan hasta 24 orígenes disponibles, con los seis últimos reservados a prueba.
Las ventanas de validación que terminan después del primer origen de prueba
siguen en embargo. Para seleccionar, además, se requieren trayectorias completas
de los seis horizontes. Así, un origen reciente con solo h=1 no pesa como un origen
con h=1..6.

Por candidato y proyecto se exige:

- al menos tres orígenes emparejados con la referencia;
- al menos dos orígenes cuyos horizontes completos no se solapan;
- cobertura de al menos 80% de las filas de referencia de ese proyecto;
- reducción de MAE de al menos 5%; si la referencia ya es exacta, se conserva.

Los umbrales son reglas conservadoras configuradas, no constantes científicas.
No garantizan significancia ni rendimiento futuro. Se guarda cada razón de
aceptación/rechazo. Si no hay suficiente evidencia, se conserva `mean3` y siguen
disponibles los candidatos shadow.

Cada familia candidata se evalúa como una política ejecutable: candidato en los
proyectos que pasan sus controles, referencia en los restantes. Todas las políticas
se comparan contra exactamente las mismas filas de validación. Se elige una familia
solo si mejora también el MAE global al menos 5%. En proyectos nuevos o candidatos
actualmente no disponibles se usa la trayectoria completa de referencia. No se
mezclan algoritmos entre horizontes de un mismo proyecto: se conserva monotonía.

La prueba final evalúa esa política congelada, incluyendo fallback. Las métricas
crudas por algoritmo de `metrics.csv` conservan su contrato anterior y pueden tener
distintas poblaciones. Para comparar candidatos usar `paired_comparisons.csv`; para
evaluar el comportamiento elegido usar `policy_backtest.csv`. No promediar WAPE de
filas ni presentar 1-WAPE como porcentaje de exactitud.

Los resultados de prueba ya inspeccionados en experimentos anteriores dejan de ser
un conjunto virgen para decisiones de arquitectura. Una nueva ejecución con el mismo
histórico sigue siendo diagnóstico de desarrollo; la confirmación requiere futuros
periodos congelados o un nuevo tramo que no se haya utilizado para decidir cambios.

## Dependencia temporal e intervalos

Diez proyectos, seis horizontes y tres cortes producen muchas filas correlacionadas.
El conteo de filas no aumenta por sí solo la independencia de la evidencia. El reporte
incluye orígenes separados por todo el horizonte. Solo con al menos tres de esos cortes
se calcula un bootstrap descriptivo de bloques móviles del tamaño del horizonte.
Usa bloques completos de orígenes, manteniendo juntos los proyectos y horizontes. Con
poco soporte se informa falta de evidencia; no se fabrica un intervalo estrecho.

Las bandas de pronóstico siguen usando errores absolutos fuera de muestra ya maduros.
Ahora exigen al menos veinte errores, tres orígenes diferentes y dos orígenes no
solapados. El reporte de calibración muestra cobertura observada, ancho y puntuación
de intervalo por horizonte y banda de stock. Esto expone heterogeneidad que un promedio
puede esconder. Las bandas siguen siendo empíricas agrupadas; no son una garantía
conformal ni un intervalo del portafolio. No sumar sus límites por proyecto.

## Interpretar GMM y Random Forest

GMM agrupa estados comerciales sin etiquetas; `gmm_analog` utiliza tasas históricas
de esos grupos para pronosticar. RF aprende supervisadamente fracciones acumuladas
de ventas; el sistema las multiplica por el stock actual. La importancia de stock
también puede reflejar esa construcción del objetivo, no solo una relación de demanda.

El BIC se registra incluso para componentes rechazados por bajo soporte. Se muestra
si el número elegido está en el límite de búsqueda. Los IDs de clusters no tienen
identidad estable entre ejecuciones. Las importancias RF guardadas son de impureza en
entrenamiento: no son causalidad ni importancia fuera de muestra. Los rangos de
entrenamiento y las entradas actuales que los exceden son diagnósticos de extrapolación,
no pruebas automáticas de deriva estadística.

## Snapshot y medición real

Se distinguen filas nuevas de correcciones históricas. Cada captura compara las
claves comunes con la anterior y registra campos/proyectos revisados. No cambia la
fuente canónica ni inventa fechas históricas de disponibilidad.

La medición busca el primer snapshot posterior a la emisión que tenga toda la ventana
del proyecto. Un snapshot incompleto de otro proyecto ya no bloquea los posteriores.
Congela el primer resultado completo, incluso si su ámbito resulta incompatible:
stock inicial distinto al emitido, nuevas entradas, revisión pendiente o saldo roto.
La exclusión queda explicada en `eligibility_reason`; una revisión posterior nunca
reescribe ese primer resultado.

Las fechas de emisión se comparan como timestamps en America/Lima:

- `eligible_for_operational_scoring`: ámbito compatible y emisión anterior al cierre
  del resultado; puede incluir una ventana ya iniciada. Medir también `issuance_delay_days`.
- `eligible_for_strict_prospective_scoring`: además exige emisión a más tardar al inicio
  de la ventana. Una ejecución habitual posterior al cierre mensual puede no cumplirlo.

La vista de monitoreo muestra ambos universos por separado. Los outcomes antiguos
reciben el valor descriptivo `LEGACY_UNASSESSED`; no se reescriben ni se certifican
retroactivamente con los nuevos controles. El histórico reconstruido continúa siendo
`HISTORICAL_DIAGNOSTIC_SHADOW`, no un replay point-in-time. Ningún comando promueve
modelos automáticamente.

## Usar en Windows

Para revisar esta rama en una carpeta independiente, conservando el trabajo actual:

```powershell
git fetch origin
git worktree add ..\bd_replica_crm_forecasting origin/feat/forecasting-robustness
cd ..\bd_replica_crm_forecasting
py -3.12 -m venv .venv
```

Configurar en esa carpeta el `.env` local de Medallio (no publicarlo). Si se usa una
instalación ya actualizada, basta con su entorno Python. Instalar y ejecutar:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\63_forecasting_demo.bat
.\scripts\64_forecasting_medallio.bat
```

La ejecución aplica la migración aditiva. Conservar los runs anteriores. Si se usa
`--once-per-month`, el run existente del mes impide otro automático; el lanzador manual
permite emitir una nueva versión sin sobrescribirlo.

Para auditar un run antiguo sin reentrenar ni cargar su joblib:

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py audit --artifacts ".\artifacts\commercial_forecasting\UUID_DEL_RUN"
```

La auditoría conserva la selección emitida en la cobertura y calcula aparte la política
que propondrían las nuevas reglas. No la presenta como una emisión del pasado. Los
artifacts antiguos sin hashes se marcan `UNAVAILABLE_LEGACY_ARTIFACTS`.

Para verificar un run nuevo:

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py verify --artifacts ".\artifacts\commercial_forecasting\UUID_DEL_RUN"
```

Código de salida 0 significa que todos los archivos coinciden con su índice. Los hashes
detectan cambios accidentales; no son firma de un tercero ni protegen contra quien pueda
reescribir también el índice. Nunca cargar joblib no confiables.

En Power BI agregar `analytics.v_commercial_forecast_coverage` y
`analytics.v_commercial_forecast_monitoring`. La cobertura es del último run v2; un run
legacy sin metadatos de cobertura no produce filas en esa vista.

## Trabajo que requiere más datos

No está implementada una predicción causal de descuentos ni recaudación. Leads,
tubería, campañas, precios efectivos y disponibilidad necesitan contratos temporales
con fecha del evento y fecha en que se conoció el dato. No basta su valor actual.
Una política estable de promoción requerirá nuevos resultados emitidos, comparación
contra referencia, error/sesgo por proyecto y horizonte y coste de la decisión.
La ampliación de modelos, tuning y variables se evaluará con nuevos cortes; no se
reutilizará repetidamente la misma prueba final para declarar una mejora confirmada.

Referencias metodológicas primarias:

- [scikit-learn: evitar fuga de información](https://scikit-learn.org/stable/common_pitfalls.html)
- [scikit-learn: límites de la importancia de variables](https://scikit-learn.org/stable/modules/permutation_importance.html)
- [Forecasting: Principles and Practice: validación temporal](https://otexts.com/fpp3/tscv.html)
