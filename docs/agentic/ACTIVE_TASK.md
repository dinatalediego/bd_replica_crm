# Active Task

Task ID: FORECAST-BI-003
Title: Diagnóstico de unidades en revisión y tablero de forecasting Cygnus
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/forecasting-robustness
Base branch: main

## Objective

Identificar los casos unitarios que ponen NP, SL y TZ en cuarentena y entregar
consultas Power BI para mostrar cobertura de stock, pronóstico, propuestas ML y
resultados medidos por horizonte con población comparable.

## Scope and decisions

ADR-016. Las filas mensuales con review_units=1 representan la repetición
del estado de una unidad actual en cada uno de los tres proyectos; el panel
agregado no contiene codigo_unidad ni causa documental. Consultas SQL locales
a v_absorcion_ventas_revision y v_absorcion_ventas_ciclos determinan qué corregir.
No se altera la fuente ni se certifica que los casos ya estén resueltos.
Queries M de Power BI son de lectura; indicadores por run/horizonte seleccionados
y outcome compatible, sin mezclar horizontes ni backtest retrospectivo.

## Evidence

- 22 pruebas locales de forecasting aprobadas; consultas M reconstruidas y
  verificadas estáticamente. CI con PostgreSQL desechable ejecutará la nueva
  prueba de las consultas reales al publicar esta revisión.
- El run anterior fue verificado en la computadora del usuario; su cobertura
  y sus resultados maduros son visibles en las vistas y artifacts locales.
- Faltan filas unitarias de la base local para determinar la proforma y el
  motivo particular de NP, SL y TZ. No se publica ningún dato comercial real.

## Next action

Revisar CI y ejecutar sql/97_commercial_forecasting/02_review_diagnostics.sql en
medallio_dw. Resolver cada unidad con evidencia documental en el origen; actualizar
la réplica local, emitir otro run y construir las dos páginas según
COMMERCIAL_FORECASTING_POWERBI.md. Conservar el run anterior para comparación.
