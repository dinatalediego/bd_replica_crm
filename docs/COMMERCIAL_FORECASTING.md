# Forecasting comercial Cygnus: implementación y evidencia

Producto adicional en Medallio. Pronostica ventas acumuladas de departamentos del
stock existente, para los siguientes 1–6 meses. Usa PostgreSQL local; no agrega
consultas ni credenciales de Redshift. No altera ventas canónicas, CI, RAW, CORE,
el ledger de absorción ni la tarea horaria existente.

## Ejecutar desde VS Code en Windows

En la carpeta de `bd_replica_crm`, con la rama de este cambio descargada:

```powershell
git fetch origin
git switch feat/forecasting-evidence-pilot
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\63_forecasting_demo.bat
```

La demo no necesita PostgreSQL ni `.env`. Usa seis proyectos ficticios `DEMO_1` a
`DEMO_6`, nunca nombres reales. Imprime la ubicación de `report.html`: abrir ese
archivo en el navegador. Todo resultado lleva `SYNTHETIC_ONLY`.

Para usar Medallio real, primero actualizar el DW por el procedimiento habitual.
Se requiere instalada `analytics.v_absorcion_ventas_mensual` con el contrato de
`sql/96_absorcion_ventas`. Si falta, instalar el contrato publicado antes:
`python scripts/schema_sync.py --only absorcion_ventas_mensual` (con el entorno activo).
El `.env` existente debe tener `POSTGRES_*`:

```powershell
.\scripts\64_forecasting_medallio.bat
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py status
```

El comando crea los objetos nuevos, captura un corte, valida, entrena, compara,
guarda estimadores y reportes, registra predicciones y mide resultados maduros.
Si la fuente no alcanza el último mes cerrado de Lima, se detiene. Una excepción
posterior al snapshot no borra ese corte; puede faltar el registro de modelo y
ser necesario repetir. No hay conexión disponible a tu PC desde esta sesión:
los resultados comerciales reales solo existirán después de ejecutar aquí.

Sin DB, se puede analizar un panel agregado y sin PII:

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py csv --input panel.csv
```

Columnas obligatorias: `month,project,sales,stock_open,stock_close,inflows,review_units`.
Mes al primer día, conteos enteros no negativos, sin duplicados ni huecos desde
inicio comercial. `stock_open + inflows - sales = stock_close` y continuidad entre
meses. No cambiar el contrato para acomodar datos defectuosos.

## Entrenamiento y temporalidad

- Promedio de ventas de hasta tres meses: referencia por proyecto, limitada por stock.
- ETS: tendencia aditiva sin estacionalidad impuesta; necesita al menos ocho meses.
- GMM + análogos: escalado robusto, mezcla diagonal regularizada, varios inicios,
  1–3 componentes elegidos por BIC solo en entrenamiento. Incluye K=1, sin forzar
  estados. Estima trayectorias de absorción ponderando pertenencias y suavizando
  hacia la media de entrenamiento.
- Random Forest: regresión supervisada de fracciones acumuladas, 80 árboles,
  profundidad 5 y mínimo 5 casos por hoja; parámetros fijados antes de la prueba.

Variables: ventas recientes, promedio tres meses, cambio de ventas, absorción,
log stock, edad observada en el panel, seno/coseno del mes. Edad es desde la primera
observación elegible, no la edad real si el histórico está truncado. Esta primera
versión usa el contrato confirmado de absorción; no inventa columnas de leads,
pricing o tubería. Esas señales requieren contratos temporales adicionales.

Para ML se necesitan al menos 24 filas maduras del portafolio, tres meses de
historia por fila de entrenamiento y los siguientes seis meses completos para
construir la trayectoria objetivo. Si cambia el horizonte en Config, el mismo
principio aplica. Las ventanas con nuevas altas, revisiones o ventas superiores
al stock inicial no sirven como análogos de este escenario. Proyectos con
`review_units > 0` quedan en cuarentena; no se presentan pronósticos engañosos.
Un lanzamiento con poca historia recibe promedio reciente, explícitamente.

Cada origen recalcula todo a partir de los meses <= corte. Solo se usan desenlaces
que ya maduraron allí. Hasta 12 orígenes móviles con seis meses posteriores
completos; últimos tres reservados a prueba final. Los anteriores seleccionan
candidatos comparando MAE sobre las mismas filas que la referencia. Se exige
al menos tres orígenes y 5% de mejora para seleccionar otra alternativa; si no,
se mantiene promedio. Es un filtro preliminar de seguimiento, no un certificado
estadístico ni una autorización de producción. El holdout final se reporta y
no se usa para elegir parámetros/modelo.

Todas las curvas son no decrecientes y <= stock. `horizon=3` son las ventas
acumuladas de los tres meses posteriores al origen. No sumar horizontes.
`monthly_increment` permite descomponer la curva en meses individuales en CSV.
El escenario no incluye nuevas altas, reincorporaciones ni retiros. Cambios de
mix, campañas y pricing son riesgos de extrapolación, no efectos causales estimados.

## La limitación temporal no se oculta

La fuente es `RECONSTRUCTED_REVISED_HISTORY`: conoce anulaciones y correcciones
actuales. El backtest está purgado respecto a los meses objetivo, pero no puede
recrear versiones históricas que no existían. Se etiqueta
`HISTORICAL_DIAGNOSTIC_SHADOW`. No afirmar “habría predicho con X precisión”.

Guardar desde ahora snapshots completos y predicciones antes del desenlace
permite medir una capacidad prospectiva auténtica. La medición usa el primer
snapshot posterior a la emisión con todos los meses del horizonte cerrado.
Resultado y versión se congelan, incluso si el histórico se corrige después.
Las tablas de evidencia impiden UPDATE/DELETE por trigger; cada ejecución es una
nueva versión. No se impide que un administrador altere el esquema: esto es
trazabilidad operativa, no un sistema criptográfico de auditoría externa.

Las predicciones toman como origen el último mes cerrado. Si se emiten el 3 de
octubre, la ventana octubre ya empezó: el campo `issued_before_window_start`
lo deja visible. `issued_before_outcome_end` distingue emisión previa al cierre.
No llamar plenamente futura a una ventana ya iniciada. Para medición, filtrar
ambos según la exigencia del uso y excluir `eligible_scope=false`.

## Incertidumbre y métricas

Se calculan MAE (departamentos), sesgo (predicción menos real), WAPE agregado
(indefinido si las ventas reales suman cero), cobertura y cantidad de rangos.
Rangos 80/95 usan errores de backtest anteriores cuyo resultado ya estaba
maduro al corte; mínimo 20 errores. Si no hay evidencia, las bandas están vacías.
Son bandas empíricas agrupadas por modelo/horizonte; dependencia temporal y
heterogeneidad de proyectos pueden alterar cobertura. No son garantía de 80/95.
No sumar límites individuales para obtener incertidumbre del portafolio.

## Evidencia que queda en cada ejecución

Carpeta `artifacts/commercial_forecasting/<run_id>/` (excluida de Git):

| Archivo | Prueba que aporta |
|---|---|
| panel.csv y quality.json | Dataset agregado, incidencias y fingerprint SHA256 |
| features.csv | Matriz de entradas y objetivos maduros |
| trained_models.joblib | Bosque, escalador, mezcla y tasas realmente ajustados |
| training_cuts.json | Entrenamiento y último desenlace utilizado en cada origen |
| model_profiles.json | Componentes GMM, soporte, perfiles y relevancias del bosque |
| backtest.csv y metrics.csv | Predicciones fuera de muestra, validación/prueba y errores |
| predictions.csv | Predicciones nuevas, stock, bandas, pertenencias y fallback |
| manifest.json | Fecha, run, snapshot, configuración, librerías, commit y limitaciones |
| report.html | Informe legible para exposición y comparación |

Abrir solo archivos joblib propios y confiables; el formato puede ejecutar código
al cargarlo. La línea git_dirty permite distinguir una prueba local de un run
hecho sobre código limpio. Preservar la carpeta junto con el registro de DB.

## Seguimiento de decisiones y Power BI

Registrar una meta acumulada y su responsable (ejemplo de sintaxis; sustituir los
valores por metas aprobadas, no copiar como si fueran reales):

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py goal --origin 2026-09-01 --project EEUU --horizon 3 --sales 10 --owner Comercial
```

Luego registrar qué se hizo con una predicción específica:

```powershell
.\.venv\Scripts\python.exe scripts\commercial_forecasting.py action --run-id UUID_DEL_RUN --project EEUU --horizon 3 --model mean3 --owner Comercial --taken "Revisión de pendientes documentales" --cost 0
.\scripts\65_forecasting_measure.bat
```

Las acciones son evidencia de ejecución, no evidencia causal de impacto.
`SIN_META` significa que no se inventó una prioridad económica.

Conector PostgreSQL de Power BI: base `medallio_dw`. Importar:

- `analytics.v_commercial_forecast_current`: pronóstico actual, meta, déficit,
  responsable, recomendación, bandas y selección por proyecto.
- `analytics.commercial_forecast_backtest`: evaluación histórica con partición.
- `analytics.v_commercial_forecast_performance`: errores prospectivos, versión de
  resultados y banderas de elegibilidad/fecha de emisión.
- `model_control.commercial_forecast_runs`: estado de evidencia y manifest.
- `decision_intelligence.commercial_forecast_actions`: acciones y costos.

Filtrar `is_selected=true` para evitar sumar candidatos. Filtrar un solo horizonte.
Vistas no tienen PII. Totales son suma de puntos por proyecto; WAPE es ratio de
sumas, no promedio de WAPE individual. Relacionar acciones por run/proyecto/horizonte/
modelo, o construir una clave compuesta; run_id por sí solo no es único en predicciones.

## Automatización mensual

No entrenar cada hora. Opcionalmente instalar la tarea Windows desde VS Code:

```powershell
powershell -File scripts\66_install_forecasting_task.ps1
```

La tarea del usuario actual comprueba a las 09:15 diariamente si falta un run del
último mes cerrado. `--once-per-month` evita reentrenar un mes ya registrado y un
advisory lock evita concurrencia. Se ejecuta con la sesión del usuario y requiere
PC disponible. No garantiza ejecución con sesión cerrada. Verificar el resultado
en el Programador de tareas. Si la réplica no terminó o hay un bloqueo de datos,
se informa un error y puede reintentarse al día siguiente. Para inspeccionar:

```powershell
Get-ScheduledTask -TaskName 'Medallio - Forecasting Comercial Mensual'
Get-ScheduledTaskInfo -TaskName 'Medallio - Forecasting Comercial Mensual'
```

El instalador reemplaza solamente la tarea con ese nombre. No cambia la tarea
horaria. La sesión Linux usada para desarrollar no puede instalar ni validar
esa tarea en tu computadora Windows.

## Cómo presentar el cambio

“Ahora tenemos una cadena verificable: datos gobernados, entrenamiento versionado,
predicciones congeladas, comparación con un método sencillo y seguimiento de
acciones. El piloto aprende patrones comerciales, estima ventas y explicita su
incertidumbre. La precisión histórica es diagnóstico; la evidencia prospectiva
se acumulará con los resultados posteriores a la emisión.”

Distinguir entrenar, predecir y ayudar. Entrenar: estimadores guardados. Predecir:
resultados emitidos antes de madurar desenlaces. Ayudar: responsables y decisiones
registrados. Beneficio causal, elasticidad de descuento y caja necesitan productos
adicionales; no se atribuyen a este piloto.

Referencias: [GMM](https://scikit-learn.org/stable/modules/mixture.html),
[Random Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html),
[validación temporal](https://otexts.com/fpp3/tscv.html).
