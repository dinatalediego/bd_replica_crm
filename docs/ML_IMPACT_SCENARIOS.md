# Impacto esperado de ML: corte comercial y escenarios en Medallio

## Contrato y alcance

El archivo `META_Y_CUMPLIMIENTO_AVANCE_POR_PROYECTO_FINAL_ML_IMPACTO.xlsx`
aporta un **corte comercial agregado** de nueve proyectos. Se importa la hoja
`Base`, con todos sus indicadores numéricos, cantidades, texto original, bloque
y nombre de origen. No se sube el Excel ni sus importes al repositorio.

`Valor Total Colocado` suma vendidos y separados; `Valor Stock Disponible`
en el bloque `5. Stock Por vender` incluye **disponibles y bloqueados**.
Estos valores no sustituyen ventas documentadas, stock físico retrospectivo ni
recaudación. El corte se identifica por fecha comercial provista por el usuario,
nombre y SHA-256 del archivo. Un corte idéntico es idempotente; una corrección
produce otra versión. Las filas importadas son inmutables.

| Objeto | Grano / uso |
| --- | --- |
| `decision_intelligence.ml_impact_snapshot` | Fecha, procedencia y hash del corte |
| `decision_intelligence.ml_impact_metric` | Corte × proyecto × bloque × indicador; todos los valores de `Base` |
| `decision_intelligence.ml_impact_scenario` | Versión × escenario y porcentaje supuesto |
| `decision_intelligence.v_ml_impact_baseline` | Montos, cantidades y diferencias de conciliación por proyecto |
| `decision_intelligence.v_ml_impact_proyecto` | Corte × proyecto × versión × escenario |
| `decision_intelligence.v_ml_impact_portafolio` | Sumas y razones calculadas al grano correcto |
| `..._actual` | Último corte importado para Power BI |
| `decision_intelligence.v_ml_impact_vs_absorcion` | Diagnóstico de conteos con el stock retrospectivo de ventas |

Los códigos de los nueve proyectos se basan en
`analytics.absorcion_inicio_proyecto` y se comprueban contra
`core.dim_proyecto` antes de cargar. Proyectos nuevos requieren un mapeo
explícito en `src/replica_cygnus/ml_impact.py`.

## Cálculo exacto

Para cada proyecto y escenario:

```text
gap_matematico = max(meta - colocado, 0)
base_stock = remanente, para EXCEL_V1
           = disponible, para DISPONIBLE_V1
impacto_potencial = base_stock × fracción del escenario
impacto_hacia_meta = min(gap_matematico, impacto_potencial)
gap_restante = max(gap_matematico - impacto_hacia_meta, 0)
cumplimiento_simulado = (colocado + impacto_hacia_meta) / meta
```

`EXCEL_V1` reproduce las tres hipótesis del libro: 5%, 10% y 20% del
**stock remanente**. `DISPONIBLE_V1` aplica las mismas fracciones solamente
al disponible, excluyendo bloqueados. La fracción es una captura adicional
hipotética del valor de stock: **no** equivale a una mejora relativa de 5% en
una tasa de conversión observada. Para demostrar uplift relativo habría que
registrar tasa base, horizonte, capacidad de contacto y experimento.

`gap_matematico` suma los gaps positivos por proyecto; también se expone
`gap_neto_portafolio_soles=max(sum(meta)-sum(colocado),0)`, que sí compensa
sobrecumplimiento entre proyectos. No son denominadores intercambiables.
El importe potencial no es caja, margen, reserva adicional garantizada ni
efecto causal atribuible al modelo.

El archivo revisado presenta un desvío entre el gap reportado y
`max(meta-colocado,0)` en Torre Nápoles. Es visible en
`diferencia_gap_soles`; nunca se corrige de forma silenciosa. Diferencias
pequeñas entre algunos importes agregados del libro y sus componentes
provienen de cifras redondeadas y se admiten hasta S/ 10 por proyecto.

## Instalar y cargar desde VS Code en Windows

En PowerShell, con el repositorio actualizado, PostgreSQL local encendido y
el archivo en una ruta local. Determinar la **fecha del corte comercial real**
antes de importar; la fecha de creación del archivo no sirve como sustituto.

```powershell
cd C:\Cygnus\projects\bd_replica_crm
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\schema_sync.py --only ml_impact
.\.venv\Scripts\python.exe scripts\import_ml_impact.py --workbook "C:\ruta\META_Y_CUMPLIMIENTO_AVANCE_POR_PROYECTO_FINAL_ML_IMPACTO.xlsx" --as-of AAAA-MM-DD --check-only
.\.venv\Scripts\python.exe scripts\import_ml_impact.py --workbook "C:\ruta\META_Y_CUMPLIMIENTO_AVANCE_POR_PROYECTO_FINAL_ML_IMPACTO.xlsx" --as-of AAAA-MM-DD --source-note "Corte comercial validado por Finanzas"
```

`--check-only` no requiere conexión; muestra los desvíos del gap por
proyecto. La carga real usa solo `POSTGRES_*` de `.env`; no consulta
Redshift ni se incorpora al ciclo horario automáticamente. Importar un
nuevo corte solo tras regenerar y verificar el reporte de negocio.
`schema_sync` instala y mantiene el contrato de vistas en el flujo normal.

La instalación supone CORE y `analytics.absorcion_ventas_mensual(date)`
existentes. Si no están, ejecutar primero el flujo local de instalación y
refresco de Medallio. La comparación con absorción es diagnóstica: esa
serie usa ventas vigentes retrospectivas, excluye separaciones y puede conocer
anulaciones registradas después de la fecha importada.

## Comprobaciones en PostgreSQL

```sql
SELECT as_of_date,scenario_set_id,scenario_code,stock_scope,
       stock_remanente_soles,stock_disponible_soles,gap_reportado_soles,
       gap_matematico_soles,diferencia_gap_soles,impacto_potencial_soles,
       impacto_hacia_meta_soles,cumplimiento_simulado,proyectos_revision
FROM decision_intelligence.v_ml_impact_portafolio_actual
ORDER BY scenario_set_id,uplift_fraction;

SELECT codigo_proyecto,nombre_proyecto,meta_soles,colocado_soles,
       gap_reportado_soles,gap_matematico_soles,diferencia_gap_soles,
       stock_remanente_soles,stock_disponible_soles,stock_bloqueado_soles,
       conciliacion
FROM decision_intelligence.v_ml_impact_baseline
ORDER BY as_of_date DESC,nombre_proyecto;

SELECT * FROM decision_intelligence.v_ml_impact_vs_absorcion
ORDER BY as_of_date DESC,nombre_proyecto;
```

Para una nueva sensibilidad, insertar un **nuevo** `scenario_set_id` con
sus filas y filtrar por él. Las versiones anteriores no se actualizan.

## Power BI y evolución

Con PostgreSQL, base `medallio_dw`, importar
`decision_intelligence.v_ml_impact_proyecto_actual` y
`decision_intelligence.v_ml_impact_portafolio_actual`. Usar un slicer
de `scenario_set_id` y `scenario_code`; mostrar un escenario a la vez.
En detalle, proyecto → impacto potencial → aporte a meta → gap restante,
junto a `diferencia_gap_soles` y `conciliacion`. Para tendencia de cortes
usar las vistas sin sufijo `_actual`, relacionando por `snapshot_id`.
No sumar porcentajes ni stock entre fechas.

El siguiente paso para medir **impacto realizado** es conservar asignación a
tratamiento/control, contacto, costo, resultado y horizonte a nivel lead o
proforma. Comparar cohortes asignadas antes de llamar a estas simulaciones
“ventas incrementales por ML”. El forecast existente en
`analytics.v_commercial_forecast_current` pronostica **unidades** a 1–6 meses;
sus cantidades no se multiplican silenciosamente por precios del corte ni
equivalen al escenario monetario.
