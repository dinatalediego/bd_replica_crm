# Datasets econométricos: historia revisada y evidencia prospectiva

Implementación aditiva local sobre PostgreSQL. Incluye la capa `evolucion_comercial`
y las siete recomendaciones: objetivos/horizontes; eventos y datasets; evidencia
por corte; exposición; composición y precios; calendario/etapas/intervenciones;
registro y evaluación de predicciones. No entrena ni promociona modelos nuevos.

## Instalación en Windows

Desde la carpeta de `bd_replica_crm`, después de actualizar a la rama de esta entrega:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
powershell -NoProfile -File .\scripts\67_install_econometric_datasets.ps1
.\.venv\Scripts\python.exe scripts\econometric_datasets.py status
```

El instalador instala los tres componentes SQL y ejecuta la carga inicial histórica.
Requiere CORE y Phase B existentes y previamente actualizados por el flujo habitual.
No modifica RAW ni vuelve a consultar Redshift. Las tablas se crean en el PostgreSQL
configurado en tu `.env`, no en GitHub.

El flujo `scripts/run_hourly.bat` -> `scripts/dw_refresh.py` incorpora el paso
`07b_econometric_datasets`, después de CORE/ventas/pricing y antes de las vistas
materializadas. Revisa tu tarea de Windows: debe apuntar a ese `run_hourly.bat`.
La primera ejecución diaria exitosa realiza el trabajo; las siguientes lo omiten.
Si falla, el próximo ciclo reintenta. Un lock evita ejecuciones simultáneas.

Si tu flujo local no utiliza ese punto de entrada, se incluye una alternativa:

```powershell
powershell -NoProfile -File .\scripts\67_install_econometric_datasets.ps1 -StandaloneTask
```

Registra **Medallio - Datasets Econometricos**, diario a las 10:15 hora del equipo,
con usuario actual y sesión iniciada, sin contraseña ni elevación. Usa datos locales;
no sustituye la tarea que actualiza RAW/CORE. `StartWhenAvailable` recupera ejecuciones
omitidas cuando sea posible. El bloqueo y el control diario evitan duplicar trabajo
si ambas rutas se activan. Solo reemplaza la tarea con ese nombre específico.
No se ha instalado ni ejecutado esta tarea en tu PC desde el entorno de desarrollo.

Ejecución manual/reproceso:

```powershell
.\.venv\Scripts\python.exe scripts\econometric_datasets.py refresh
.\.venv\Scripts\python.exe scripts\econometric_datasets.py refresh --backfill
```

`refresh` actualiza el histórico reconstruido, las etiquetas y la demanda; captura
el primer snapshot del día. `--backfill` también busca snapshots antiguos compatibles
cuando ya existía una ejecución exitosa. La primera carga lo hace automáticamente.
El control diario solamente aplica con `--once-per-day`, usado por la programación.
No reescribe el snapshot ni las variables observadas del mismo día.

## Inventario de datos y política de actualización

| Objeto | Clave/grano | Histórico | Nuevos datos/correcciones |
|---|---|---|---|
| analytics.fact_evento_comercial | evento × versión | Ciclos documentales y ledger local | Append: correcciones y tombstones, no borrado de evidencia |
| analytics.snapshot_unidad_diario | unidad × día | Snapshots antiguos con fecha real de captura compatible; nunca inventados | Primera observación diaria inmutable |
| features.dataset_unidad_prediccion | unidad × corte × evidencia | Fin de mes desde inicio de proyecto; RECONSTRUIDO | Historia revisada actualizable; OBSERVADO inmutable |
| features.unidad_prediccion_resultado | unidad × corte × horizonte | 30/60/90/180 días; sin etiquetas de futuro no maduro | Se actualiza con verdad revisada; cambios se auditan |
| features.unidad_resultado_version | resultado × versión | Primera medición y posteriores correcciones | Append; evaluación conserva primer resultado maduro sin alertas y con fuente fresca |
| analytics.panel_demanda_proyecto_semana | proyecto × semana | Fuentes RAW locales verificadas | Recalculado diariamente, con estado de cada fuente |
| analytics.historial_oferta_unidad | unidad × evidencia de precio | Capturas antiguas/importación documentada | Append; LISTA, OFERTADO y CIERRE separados |
| analytics.historial_etapa_proyecto | proyecto × versión | Solo evidencia observada o futura importación documentada | Nueva versión cuando cambia la composición de estados de construcción |
| analytics.intervencion_comercial | intervención documentada | Importación con vigencia, fuente y fecha disponible | Nueva clave para correcciones; no sobrescribir |
| analytics.contexto_mercado_mes | mercado × indicador × mes × publicación | Importación de series fechadas | Nueva publicación/versionado; conserva ingested_at |
| analytics.proyecto_mercado_econometria | proyecto | Mapeo explícito de mercado | Importar correspondencia; no se adivina ubicación comparable |
| model_control.prediccion_unidad | predicción emitida | No admite fingir predicciones pasadas | Inserción del modelo consumidor antes de la ventana objetivo |
| analytics.registro_prediccion_resultado | predicción de proyecto y resultado | Reutiliza piloto forecasting existente | Su entrenamiento/medición conserva su programación existente |
| model_control.econometria_runs / econometria_fuentes | ejecución / fuente | Evidencia operativa desde instalación | Estado, fecha, avisos de contrato; sin PII |

## Disponibilidad real y universo

Se hereda `v_absorcion_ventas_unidad`: proyectos con inicio registrado, departamentos
y NP solo NP-A. Proyectos sin inicio siguen fuera y visibles en el control anterior.
Estado actual usa venta canónica, estados CORE explícitos y bloqueos. "No disponible"
no se clasifica como disponible. Estados no reconocidos -> disponibilidad NULL.
Los snapshots antiguos sin atributos conservan NULL y alerta de revisión; no reciben
atributos actuales como si se hubieran conocido antes.

El panel reconstruido supone alta inicial conjunta y anulación retrospectiva como el
mart aprobado. Su exposición no es disponibilidad diaria certificada. El ledger
preserva liberaciones/movimientos observados con cobertura parcial. No interpolamos
los días faltantes entre snapshots ni afirmamos conocer todas las liberaciones pasadas.
La fuente ABSORCION_CICLOS representa separación documental, minuta y anulación;
LEDGER_TRANSICION representa movimientos físicos. **No sumar ambas fuentes como
si fueran ventas distintas.** Las métricas de ventas usan exclusivamente la primera.
La desaparición de un evento de la fuente crea una versión inactiva, no lo borra.
`fecha_registro_origen` puede ser NULL: el código no confunde fecha del evento con
fecha real de registro. `disponible_desde` es cuándo esta capa detectó esa versión.

## Demanda y cobertura

Contratos declarados en `config/econometric_sources.json`, comprobados contra el
esquema local antes de consultar. Predeterminados:

- Captación: `clientes_proyectos.fecha_creacion`, filas y clientes únicos por proyecto/semana.
- Asignación: `clientes_proyectos.fecha_asignacion`; no se presenta como captación nueva.
- Proformas: `proforma_unidad.fecha_creacion`, códigos de proforma distintos y unidades del universo habilitado.
- Interacciones: `interacciones.fecha_creacion`, ID distinto. Es fecha de registro,
  no necesariamente la fecha en que se realizó una visita.
- Visitas: NULL hasta configurar `visit_column` y `visit_values` con etiquetas verificadas.

Fuentes ausentes/columnas faltantes -> métricas NULL y aviso PENDIENTE. No se añaden
consultas a Redshift. Fechas con tipos incompatibles fallan visiblemente. No se
exportan documentos de clientes: la deduplicación ocurre dentro del agregado SQL.
Antes de la primera semana observada de cada fuente/proyecto, métricas NULL; después,
una semana sin registros se cuenta como cero. Esto presupone retención continua
posterior al primer registro y debe contrastarse con cobertura local.
La captura de leads/interacciones es por proyecto: no siempre puede discriminar
interés NP-A frente a NP-B. Esta limitación no se traslada al stock/ventas por unidad.
Las proformas múltiples de un cliente son actividad de cotización, no clientes únicos.

## Datasets para modelos

`features.v_dataset_unidad_entrenamiento` une predictores y objetivos:

- Variables al corte, moneda, composición, área/precio relativos, edad y calendario.
- Para observados, demanda de cuatro semanas completas previas; se congela al capturar.
- Ventana objetivo: desde el día siguiente al corte hasta corte + horizonte, inclusivo.
- Madurez: ventana terminada antes del día de ejecución. No equivale por sí sola a
  certificación de completitud de RAW. Revisar runs, frescura y calidad.
- Minutas brutas/anulaciones se conservan separadas; `venta_vigente` usa verdad canónica revisada.
- `elegible_validacion_prospectiva` exige OBSERVADO, disponibilidad, madurez, frescura
  del corte y ausencia de alertas. No sustituye revisión de cobertura de resultados.
- Los labels se revisan; las versiones previas sobreviven. La evaluación de predicciones
  emitidas consulta el primer resultado maduro sin alertas y con fuente fresca para no reescribir el marcador a posteriori.

Para supervivencia: unidades no vendidas son censuradas, no descartadas. Para conteos:
usar exposición/stock y validar por fecha, nunca repartir aleatoriamente filas de
la misma trayectoria. Separar entrenamiento y evaluación por fecha y horizonte,
con embargo suficiente para que las etiquetas de entrenamiento ya hayan madurado.
Comparar baseline simple antes de promover modelos. Se preparan datasets y registros;
esta entrega no estima nuevos coeficientes ni garantiza mejoras predictivas.

`features.v_estacionalidad_panel` expone mes calendario, edad, año, stock, ventas,
exposición y mezcla de dormitorios/área. Su evidencia es reconstruida. No incluir
edad, calendario y cohorte de lanzamiento de forma completamente irrestricta:
existe dependencia determinista. Estacionalidad requiere suficiente solapamiento
entre proyectos/edades/calendarios, no solo muchos registros unidad-mes.

## Precios e importaciones externas

La captura diaria incluye precio LISTA. No inventa ofertas ni precios de cierre.
El mart de pricing anterior puede haber usado moneda por defecto y fechas retroactivas:
sus filas se conservan con calidad LEGACY y **no entran al índice observado**.
`analytics.v_econometria_serie_precios` usa disponibilidad real de la observación,
moneda separada y cesta fija. Sin cesta completa, índice NULL y cobertura visible.
No es índice real deflactado ni hedónico; base 100 no implica estacionariedad.

Plantillas de cabeceras en `examples/econometria/*.csv`. Completar con evidencia real:

```powershell
.\.venv\Scripts\python.exe scripts\econometric_datasets.py import-csv --kind mercado --file .\examples\econometria\mercado.csv
.\.venv\Scripts\python.exe scripts\econometric_datasets.py import-csv --kind proyecto_mercado --file .\examples\econometria\proyecto_mercado.csv
.\.venv\Scripts\python.exe scripts\econometric_datasets.py import-csv --kind intervenciones --file .\examples\econometria\intervenciones.csv
.\.venv\Scripts\python.exe scripts\econometric_datasets.py import-csv --kind ofertas --file .\examples\econometria\ofertas.csv
```

Fechas YYYY-MM-DD; fechas-hora incluyen zona, por ejemplo `2026-10-07T10:00:00-05:00`.
Valores decimales con punto, sin símbolos monetarios. Reimportar una fila idéntica no
duplica; misma clave con contenido diferente falla para exigir nueva versión.
Ofertas importadas quedan pendientes de auditoría aunque el CSV diga OBSERVADO.
No se agregan automáticamente a predictores ni se mezclan lista/cierre.
Los CSV iniciales solo contienen cabeceras; tasas, inversión, visitas y ofertas sin
fuente permanecen sin datos. No hay un proveedor/API externo configurado.
`v_contexto_mercado_por_corte` respeta publicación e ingestión para cortes observados;
para reconstruidos permite historia publicada al corte, etiquetada como diagnóstico.

## Validación reproducible

Pruebas Python: `python -m pytest tests/test_econometric_imports.py tests/test_econometric_demand.py tests/test_dw_refresh_contract.py`.
SQL: definir `ECONOMETRIC_TEST_DSN` de una base VACÍA descartable y ejecutar
`python -m pytest tests/integration/test_econometric_postgres.py`.
Alternativa aislada PGlite: `tests/integration/run_econometric_pglite.cjs` documenta
instalación temporal. Cubre reinstalación, refresh, anulaciones, correcciones,
tombstones, precios, censura, inmutabilidad y restricciones temporales.
Medallio real, permisos del Programador de tareas y duración con volumen productivo
requieren ejecución local. No se reactivan GitHub Actions.

## Primeras consultas para explorar datasets

```sql
-- Diagnóstico histórico: departamentos aún pendientes al cierre del mes.
-- No presentar este resultado como un backtest point-in-time.
SELECT * FROM features.v_dataset_unidad_entrenamiento
WHERE evidencia='RECONSTRUIDO' AND pendiente_venta AND maduro AND horizonte_dias=90;

-- Evaluación prospectiva: tarda en madurar después de iniciar capturas.
SELECT * FROM features.v_dataset_unidad_entrenamiento
WHERE elegible_validacion_prospectiva AND horizonte_dias=90;

SELECT * FROM analytics.v_econometria_cobertura;
SELECT * FROM analytics.v_econometria_serie_precios ORDER BY codigo_proyecto,mes;
SELECT * FROM model_control.econometria_fuentes WHERE estado<>'OK';
```
