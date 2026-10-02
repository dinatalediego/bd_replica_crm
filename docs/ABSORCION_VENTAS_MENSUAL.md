# Absorción mensual por ventas desde enero de 2024

## Contrato aprobado el 02/10/2026

Stock de departamentos pendiente de venta, reconstruido con todo el universo de
`raw_cygnus.unidades` que ya replica `core.dim_unidad`. Incluye vendidos y no vendidos;
no usa el estado comercial actual para fechar una venta ni para recortar el universo.
El alta de TODO el proyecto ocurre el primer día del mes de la fecha más antigua
entre el adjunto y la primera venta documental permitida. La tabla original se
conserva; `v_absorcion_inicio_proyecto` expone ambos valores y una observación.
La evidencia de ventas posteriormente anuladas también puede acreditar un inicio
anterior, aunque esas ventas no se descuenten. Es stock reconstruido, no observado.
Los 17 códigos se conservan como texto, incluido `001`. Proyectos sin fecha del
adjunto permanecen en `v_absorcion_proyectos_sin_inicio` para completar su configuración.

### Reglas ratificadas tras revisar los datos locales

- `datos_extras` de entidad proforma, nombre `fecha_de_minuta`, relacionado por
  `codigo = codigo_proforma` del ciclo de Separacion, tiene prioridad. Se reutiliza
  el parser existente y se toma la última actualización/id. Un valor poblado inválido
  queda excluido; nunca activa silenciosamente el respaldo.
- Sin pago fechado, se permite la primera fecha del proceso Venta **Activo** de la
  misma proforma/unidad, únicamente cuando tanto la separación original como la
  analítica son anteriores a 2026. Se mantiene íntegro el veto vigente desde 2026.
- Una fecha documental anterior a la separación se acepta, conservando la fecha
  real y una observación. El desplazamiento legacy del stock no descarta ventas.
  No se exige que el ledger haya aplicado una transición de venta.
- Una Anulacion fechada hasta hoy de la misma proforma/unidad excluye el ciclo de
  todos los meses, incluso si sucede después de la venta o el mismo día. Se conserva
  el filtro existente que descarta el flujo `Desistimiento de visita`; no se filtra
  estado de Anulacion, conforme a la fuente usada por Phase B. Una venta posterior
  de otra proforma sí puede contar. Las caídas de separación no mueven stock.
- La población de ciclos viene de Phase B y conserva las exclusiones de negocio.
  Se consultan procesos y extras de la réplica PostgreSQL local, sin nuevas cargas
  Redshift. Los controles y ledger globales permanecen intactos.

Más de una venta vigente elegible por unidad permanece pendiente, sin elegir una
arbitrariamente. Una venta futura solo descuenta al alcanzar su fecha. Las ventas
previas a enero de 2024 reducen el saldo inicial de enero. El estado comercial actual
solo ayuda a detectar pendientes; no sustituye la fecha documental.

`v_absorcion_ventas_observaciones` entrega los casos resueltos y pendientes con unidad,
proforma, fechas, IDs de origen y comentarios, sin información personal. Los campos `resultado_canonico` y `reconciliation_status` conservan el diagnóstico
del modelo anterior; `calidad_ciclo` determina la elegibilidad de ESTE reporte. La vista
`v_absorcion_ventas_revision` contiene los pendientes; una excepción aceptada con
comentario ya no es automáticamente un pendiente. Las anulaciones se conservan como
evidencia aunque su venta no figure en los totales.

Este cuadro es retrospectivo: una anulación conocida hoy cambia meses anteriores,
incluso al consultar un corte antiguo. La futura tabla de seguimiento por eventos
(venta, anulación, reventa y vigencia temporal) queda como ampliación pendiente. No
se presenta el ledger existente como sustituto de ese seguimiento de anulaciones.

## Objetos para Power BI

| Objeto en analytics | Grano / propósito |
| --- | --- |
| `absorcion_inicio_proyecto` | Fechas originales del adjunto |
| `v_absorcion_inicio_proyecto` | Inicio efectivo, primera evidencia y observación |
| `v_absorcion_ventas_observaciones` | Casos documentados, aceptados o excluidos |
| `v_absorcion_ventas_unidad` | Un departamento, fecha de alta, fecha de venta, proforma, método y revisión |
| `v_absorcion_ventas_mensual` | Proyecto/mes desde enero 2024 hasta hoy, zona America/Lima |
| `v_absorcion_ventas_ciclos` | Evidencia por proforma/unidad; motivo de exclusión y IDs de origen |
| `v_absorcion_ventas_revision` | Unidades que requieren revisión |
| `v_absorcion_proyectos_sin_inicio` | Proyectos con departamentos que no figuran en el adjunto |

Las vistas leen los ciclos procesados y la evidencia RAW local vigente; no requieren un segundo backfill ni otro
job de refresh. `schema_sync.py` instala el componente con checksum dentro del flujo
normal antes del refresh de CORE y Phase B. Al terminar el refresh normal, las vistas
reflejan las fuentes procesadas. En Import, Power BI necesita su propia actualización.
`ultima_actualizacion_ciclos` en el detalle muestra la frescura del ciclo; la fecha de
corte del cuadro es la fecha del reporte y NO garantiza que la réplica esté al día.

## Instalación desde VS Code (PowerShell)

Desde el repositorio local, con los cambios locales guardados y la rama descargada:

```powershell
git fetch origin
git switch --track origin/feat/absorcion-mensual-ventas-2024
.\.venv\Scripts\python.exe scripts/schema_sync.py --only absorcion_ventas_mensual
.\.venv\Scripts\python.exe scripts/dw_refresh.py --mode manual --local-only
```

Si la rama ya existe: `git switch feat/absorcion-mensual-ventas-2024` y
`git pull --ff-only`. `--local-only` reutiliza los RAW locales; no los actualiza desde
Redshift. El refresco horario normal ya incorpora el nuevo componente al ejecutarse
con esta versión. El protocolo de actualizaciones existente no cambia.

Ejecutar `sql/96_absorcion_ventas/02_validation.sql` sobre `medallio_dw`. No declarar
conciliado el resultado hasta revisar las incidencias y la frescura de las fuentes.

## Cuadro Power BI

Conector PostgreSQL, base `medallio_dw`, vista `analytics.v_absorcion_ventas_mensual`.
Matriz: filas `nombre_proyecto`; columnas `periodo_mes` (orden cronológico); valores
`stock_final`. Para detalle mensual usar también `stock_inicial`, `ingresos_mes`,
`ventas_mes`, `ventas_acumuladas`, `absorcion_mensual` y `unidades_revision`.

`stock_final = stock_inicial + ingresos_mes - ventas_mes`.
`absorcion_mensual = ventas_mes / (stock_inicial + ingresos_mes)`; denominador cero
produce NULL. `absorcion_acumulada = ventas_acumuladas / total_departamentos` una vez
iniciado el proyecto. Meses previos al inicio tienen stock/ventas cero y tasas NULL.

No sumar saldos de stock entre meses: son saldos al corte. Las ventas mensuales sí
son aditivas. Para una tasa de varios proyectos dividir las sumas del numerador y
denominador; no sumar porcentajes. El mes actual tiene `mes_parcial=true` salvo fin de mes.

Consulta reproducible con corte explícito:

```sql
SELECT * FROM analytics.absorcion_ventas_mensual(DATE '2026-10-02')
ORDER BY periodo_mes,nombre_proyecto;
```

El corte reproduce la aritmética sobre la evidencia ACTUAL: cambios retrospectivos
al universo, fechas o ventas pueden cambiar el pasado. No es una consulta de versiones
históricas. Sin stock histórico de unidades borradas no se pueden recuperar esas bajas.

## Validación

Pruebas ejecutables en `tests/integration/test_absorcion_ventas_postgres.py` sobre una
base PostgreSQL desechable. `ABSORCION_TEST_DSN` debe apuntar solo a una base vacía de
pruebas: el fixture crea esquemas y revierte cada caso. CI usa un servicio PostgreSQL 16.
Sin DSN puede usarse el paquete opcional pgserver; sin ambos, pytest marca esas pruebas
como omitidas. Las pruebas no se conectan a Medallio ni a Redshift.

## Compatibilidad con instalaciones antiguas

La instalación inicial podía fallar con `InvalidTableDefinition` al reemplazar
`v_ciclo_comercial_reconciliado`: su `c.*` incorporaba columnas nuevas de Phase B
en posiciones intermedias. El componente ahora instala su propio adaptador con
columnas explícitas, conservando la semántica de reconciliación. No renombrar
columnas ni usar DROP CASCADE sobre la vista legacy. Tras descargar la corrección,
repetir `schema_sync.py --only absorcion_ventas_mensual`; el checksum y el estado
FAILED anterior provocan el reintento automático.

## Consultas de entrega y revisión

```sql
SELECT * FROM analytics.v_absorcion_inicio_proyecto ORDER BY nombre_proyecto;
SELECT * FROM analytics.v_absorcion_ventas_observaciones
ORDER BY codigo_proyecto, codigo_unidad, codigo_proforma;
SELECT * FROM analytics.v_absorcion_ventas_revision ORDER BY codigo_proyecto,codigo_unidad;
```

Exportar la segunda consulta a CSV para conservar los casos comentados en una fecha.
Las vistas son vivas; no constituyen un historial inmutable de cambios de la fuente.
La validación sintética comprueba reglas y saldos. Los nuevos totales reales requieren
reinstalar el componente en Medallio y ejecutar `02_validation.sql`.
