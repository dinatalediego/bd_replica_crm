# Absorción mensual por ventas desde enero de 2024

## Contrato aprobado el 02/10/2026

Stock de departamentos pendiente de venta, reconstruido con todo el universo de
`raw_cygnus.unidades` que ya replica `core.dim_unidad`. Incluye vendidos y no vendidos;
no usa el estado comercial actual para fechar una venta ni para recortar el universo.
El alta de TODO el proyecto es el primer día del mes del CSV `inicio por proyecto.csv`.
Es un supuesto explícito de reconstrucción, no un snapshot histórico observado.
Los 17 códigos se conservan como texto, incluido `001`. Los proyectos sin fecha del
adjunto aparecen en `v_absorcion_proyectos_sin_inicio` y no se les inventa un alta.

Se reutiliza `analytics.v_ciclo_comercial_reconciliado`, no se duplica el cálculo de
fecha de venta ni se vuelve a consultar Redshift. Se conservan los controles:
`fecha_de_minuta` tiene prioridad; el respaldo `Venta.fecha_inicio` solo es válido
para separaciones anteriores a 2026, conforme a `fecha_separacion` del ciclo vigente.
Se exigen venta canónica reconciliada y fecha validada. Los casos temporales inválidos,
venta/caída el mismo día o discrepancias continúan fuera del conteo y visibles en revisión.
No cambia el tratamiento existente de anulaciones de ventas; no se introduce una
nueva política de reversión. Las separaciones y caídas de separación no restan ni suman
unidades en ESTE cuadro. Una caída anterior a una venta válida de otro ciclo no genera
movimientos intermedios. El ledger operativo original conserva su propio significado.

Más de una venta elegible por unidad requiere revisión: no se selecciona una al azar
ni se descuenta dos veces. Ventas anteriores al ingreso del proyecto se exponen como
incidencia. Una venta futura solo descuenta stock cuando alcanza el corte consultado.
Las ventas anteriores a enero de 2024 sí reducen el stock inicial de enero.

## Objetos para Power BI

| Objeto en analytics | Grano / propósito |
| --- | --- |
| `absorcion_inicio_proyecto` | Tabla editable de supuestos de ingreso por proyecto |
| `v_absorcion_ventas_unidad` | Un departamento, fecha de alta, fecha de venta, proforma, método y revisión |
| `v_absorcion_ventas_mensual` | Proyecto/mes desde enero 2024 hasta hoy, zona America/Lima |
| `v_absorcion_ventas_ciclos` | Evidencia por proforma/unidad; motivo de exclusión y IDs de origen |
| `v_absorcion_ventas_revision` | Unidades que requieren revisión |
| `v_absorcion_proyectos_sin_inicio` | Proyectos con departamentos que no figuran en el adjunto |

Las vistas leen los resultados vigentes; no requieren un segundo backfill ni otro
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
