# Evidencia de ejecución sintética

**No son resultados de Cygnus.** Se ejecutó el piloto completo con seis proyectos ficticios y 42 meses por proyecto.

Run: `a50e1b98-a4d3-4153-b9b1-870cae2d2074`. Dataset SHA256: `87faaf8a55eafb4efdf7e13a3e25ec06f4ba1733e96d5ed5542554592d76f7bf`.
Filas maduras en entrenamiento final: 204. Selección en validación: `random_forest`.

Se guardaron estimadores ajustados, probabilidades GMM, perfiles, backtest, predicciones nuevas y reporte HTML. La selección utiliza validación con desenlaces maduros antes del primer corte de prueba; las ventanas solapadas quedan en embargo. En la demo final se seleccionó Random Forest, sin usar la prueba final para elegirlo.

| Modelo | Horizonte acumulado | Casos de prueba | MAE (departamentos) | WAPE |
|---|---:|---:|---:|---:|
| ets | 1 | 18 | 2.918 | 36.731% |
| ets | 3 | 18 | 7.156 | 28.435% |
| ets | 6 | 18 | 11.539 | 21.772% |
| gmm_analog | 1 | 18 | 2.400 | 30.205% |
| gmm_analog | 3 | 18 | 5.397 | 21.447% |
| gmm_analog | 6 | 18 | 14.394 | 27.159% |
| mean3 | 1 | 18 | 3.259 | 41.026% |
| mean3 | 3 | 18 | 7.444 | 29.581% |
| mean3 | 6 | 18 | 15.556 | 29.350% |
| random_forest | 1 | 18 | 2.981 | 37.525% |
| random_forest | 3 | 18 | 5.935 | 23.584% |
| random_forest | 6 | 18 | 8.372 | 15.796% |

Los tres orígenes de prueba final se mantuvieron separados de la selección. Esta evaluación sintética comprueba ejecución y trazabilidad; no demuestra capacidad predictiva comercial real. El histórico real de absorción se etiqueta diagnóstico hasta disponer de evidencia prospectiva.

Para reproducir: `python scripts/commercial_forecasting.py demo`. La identidad de ejecución cambia; el panel sintético, semilla y configuración son reproducibles. La CI publica los artefactos sintéticos descargables de su propio run.
