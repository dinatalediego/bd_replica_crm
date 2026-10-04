# Active Task

Task ID: FORECAST-ROBUSTNESS-002
Title: Arquitectura robusta y evidencia comparable de forecasting
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/forecasting-robustness
Base branch: main

## Objective

Fortalecer la arquitectura del piloto ya fusionado en PR #39 con controles
 ejecutables de selección, soporte temporal, cobertura y trazabilidad.

## Scope and decisions

ADR-015. Selección en validación por proyecto; políticas completas comparadas con
la misma población y fallback explícito. Stock cubierto y cuarentenas visibles.
Snapshot revisions, código/hashes archivados, medición con ámbito compatible y
fechas de emisión en Lima. GMM/RF permanecen candidatos shadow; conservar mean3
cuando la evidencia no cumple los umbrales. No se modifican ventas canónicas ni
se consulta Redshift. No hay acceso a PostgreSQL real del usuario.

## Evidence

- 144 pruebas unitarias de plataforma y 106 de decision_engine aprobadas.
- Compilación Python y notebook sintético ejecutados de extremo a extremo.
- Auditoría privada de artifacts anteriores ejecutada sin cargar joblib; integridad
  de nuevos artifacts verificada. Datos comerciales no publicados en GitHub.
- Integración PostgreSQL pendiente de CI; el entorno local no permite iniciar
  el servidor desechable como usuario sin privilegios.
- La prueba histórica inspeccionada sigue siendo diagnóstico de desarrollo;
  no se afirma ganancia de precisión futura.

## Next action

Revisar PR y CI. Usar docs/COMMERCIAL_FORECASTING_ROBUSTNESS.md para instalar en una
carpeta independiente, auditar runs anteriores y emitir nuevas versiones en Medallio.
Medir futuros resultados congelados; resolver cuarentenas con evidencia documental.
