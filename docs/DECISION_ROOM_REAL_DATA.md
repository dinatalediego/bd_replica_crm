# Sala de decisiones Medallio — puente mínimo de datos reales

## Estado comprobado el 2026-10-16

- El repositorio define `analytics.comercial_proyecto_mes` con stock y ventas mensuales gobernadas, más `analytics.agg_ventas_mensual` con separaciones brutas. La historia del primer mart es retrospectiva revisada, no snapshots emitidos en cada mes.
- `analytics.v_commercial_forecast_monthly` expone incrementos mensuales de predicciones acumuladas a 1–6 meses, con run, modelo y evidencia. Puede faltar, estar desactualizada o excluir proyectos con unidades en revisión.
- El piloto remoto `medallio_pilot.project_month` contenía únicamente 24 filas `SYNTHETIC` de dos proyectos ficticios; no había carga real. El registro remoto de Decision/Action/Outcome/Economic Value tenía cero filas. No se debe presentar ese piloto como producción.
- Los esquemas remotos `medallio_*` existían, pero carecían de tablas replicadas; `medallio_admin.table_registry` y `sync_runs` estaban vacíos. La Sala no puede conectarse a un dataset real online hasta que exista una publicación gobernada.

## Contrato inicial

`scripts/export_decision_room.py` lee PostgreSQL local en modo solo lectura y emite `medallio_decision_room_v1` para importar en el navegador. El archivo contiene proyecto, mes, stock, ventas/minutas gobernadas, separaciones brutas cuando existan, revisión de unidades y pronóstico seleccionado si está disponible. No contiene clientes, teléfonos, correos, unidades ni precios individuales. Sigue siendo información comercial sensible: conservarlo fuera de Git y compartirlo según la política de la empresa.

| En la Sala | Fuente local | Estado y límite |
|---|---|---|
| Proyecto y meses | `analytics.comercial_proyecto_mes` | Disponible si la tarea local lo instaló y refrescó. |
| Stock y ventas/minutas | `analytics.comercial_proyecto_mes` | Historia revisada; stock de este mart no equivale a un snapshot histórico inmutable. |
| Separaciones brutas | `analytics.agg_ventas_mensual` | Universo distinto; no dividir automáticamente minutas/separaciones como tasa de cohorte. |
| Pronóstico de minutas | `analytics.v_commercial_forecast_monthly` | Solo 1–6 meses y proyectos elegibles. Bandas 80 son **acumuladas**, no mensuales. |
| Leads totales | Pendiente de mart único de CRM | `staging.portal_leads_base` cubre portal, no necesariamente toda la captación. Exporta `null`. |
| Ingresos y margen | Pendiente de precio de venta conciliado, costos y gasto de campaña | `fact_proyeccion_pricing` usa supuestos y su moneda requiere validación. Exporta `null`. |
| Captación, seguimiento, descuento, subida de precio | Pendiente de intervenciones y elasticidades estimadas | Desactivados en modo real. Nunca aplicar coeficientes de la demo a datos reales. |
| Meses hasta stock cero | Ventas observadas y forecast 1–6 | Solo puede mostrarse como cobertura dentro del horizonte emitido; extrapolación a 12+ meses requiere otro contrato. |

## Ejecución en el PC

En el entorno habitual del repositorio, después del refresh de Medallio, usa `POSTGRES_*` del `.env` existente. `MEDALLIO_DSN` es una alternativa opcional:

```powershell
python scripts/export_decision_room.py --project MT --project NP --from-month 2025-01-01 --output artifacts/decision_room/medallio_real.json
```

Se pueden elegir de uno a cinco proyectos. El exportador rechaza meses duplicados, stock inconciliable, conteos negativos y archivos que ya existen. No escribe en PostgreSQL, Supabase ni la Sala. En la Sala privada, selecciona el archivo con **Importar datos Medallio**; la lectura sucede en tu navegador y el archivo no se envía al servidor. Si el pronóstico falta, la interfaz muestra solo la historia disponible.

La verificación pendiente en el PC incluye confirmar las relaciones instaladas, el corte de la tarea horaria, las incidencias de stock, la cobertura del último forecast y el universo de separaciones para cada proyecto. Este repositorio remoto no da acceso al PostgreSQL local.

## Mínimo para actualización automática

1. **Contrato comercial agregado** por proyecto y mes: leads únicos con deduplicación temporal, separaciones por criterio aprobado, minutas/ventas canónicas, stock y corte, con pruebas de conciliación y frescura.
2. **Contrato monetario** en PEN con precio de venta o ingreso documentado por unidad, costo de construcción/terreno y gasto de captación asignable. Diferenciar margen bruto, contribución y caja. Acordar moneda y tipo de cambio en pricing.
3. **Forecast emitido** a 12 meses, intervalos calibrados por horizonte y cobertura publicada; no extender una banda acumulada a meses futuros sin backtest. Registrar versión, fecha de emisión y elegibilidad.
4. **Modelo de intervenciones**: presupuesto y leads por canal/campaña, timestamps de asignación y primer contacto, descuentos ofrecidos/aprobados, lista de precios versionada y costos. Identificar cohortes y posibles confusores antes de estimar respuesta a los cuatro controles.
5. **Publicación segura** de solo agregados aprobados a una API privada con identidad y permisos de servidor. La Sala consulta esa API; ningún secreto ni acceso SQL privilegiado vive en el navegador. Registrar corte, hash, estado de calidad y fecha de última sincronización.
6. **Ciclo de decisión**: persistir Decision, Action, Outcome y Economic Value con baseline y fórmula versionados. Medir realizado tras maduración; valor esperado y observado permanecen separados. Revisiones de negocio y ciencia de datos antes de ejecutar cambios reales.

El siguiente hito verificable es ejecutar el exportador en el PC y validar un archivo real de uno o dos proyectos. Solo entonces tiene sentido habilitar la publicación automática y los controles económicos.
