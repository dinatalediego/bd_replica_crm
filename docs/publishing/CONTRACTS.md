# Contratos v1 y consumidor Android

Los schemas canónicos están dentro del paquete Python:
`src/replica_cygnus/publishing/schemas/*.schema.json` (JSON Schema 2020-12).
Se incluyen como package data al instalar. Son contratos cerrados: campos
inesperados, valores no finitos, fechas inválidas y versiones desconocidas fallan.

| Archivo | Contrato | Contenido |
|---|---|---|
| `data.json` | data-pack, 1.0.0 | Datos agregados, indicadores, grano y calidad. |
| `model.json` | model-pack, 1.0.0 | Modelo, parámetros, evaluación y resultados por proyecto. |
| `story.json` | story-pack, 1.0.0 | Historia, findings, decisiones y Wisdom Cards. |
| `scenario.json` | scenario-pack, 1.0.0 | Supuestos y resultados relacionados con el modelo. |
| `manifest.json` | manifest, 1.0.0 | Versión, clasificación, commit, hash del builder y hashes/tamaños. |

El sobre v1 se distribuye como ZIP **sin compresión** de exactamente esos cinco
archivos, sin directorios. Cada JSON debe ocupar como máximo 4 MB, el ZIP 20 MB.
La demo ocupa aproximadamente 15 KB. Un importador debe rechazar duplicados,
archivos extra, rutas de extracción, entradas comprimidas/cifradas y límites
excedidos. No extraer ciegamente con `extractAll`. No cargar pickle/joblib ni código
procedente de un pack. El pack no puede definir fórmulas arbitrarias ejecutables.

Los cuatro documentos comparten procedencia: fuente, semántica temporal, corte,
fecha de generación, hash del dataset, transformación y limitaciones. `PRIVATE`
no se puede cambiar por `SYNTHETIC` para habilitar publicación. Solo la fixture
exacta reconocida tiene procedencia sintética certificada por este builder.
Una nueva demo requiere código/versionado explícito, no una casilla de confianza.

## Semántica del modelo y experimento

`prediction = min(stock_close, mean(sales[-3:]))`, horizonte de un mes. Objetivo:
unidades vendidas del inventario fijo. Ventas y stocks observados en este contrato
son conteos; el resultado esperado puede ser fraccional. Evaluación: tres orígenes
finales de cada proyecto, prediciendo con tres meses estrictamente anteriores.
No hay selección de hiperparámetros. `training_period` describe el período de datos
usado para emitir el resultado final, no una afirmación de entrenamiento ML.
MAE agregado sobre esos casos; no una evaluación prospectiva de producción.

Un control: `velocity_multiplier` en `[0.5,1.5]`, original `1.0`.
`scenario = min(stock, prediction * multiplier)`; no redondear hasta presentar.
Escenarios guardados 0.75, 1.0 y 1.25. No son percentiles ni intervalos.
`uncertainty.status = NOT_ESTIMATED` es información honesta, no dato ausente a
rellenar con una banda arbitraria.

## Relación y evolución

Story referencia Data y Model; Finding referencia Indicator; Decision referencia
Finding, Model y Scenario; Wisdom referencia Finding. Todos los IDs se validan.
La validación semántica también recalcula resultados, MAE y escenarios.
Nunca sumar distintas releases ni horizontes de modelos futuros sin revisar grano.

Tipos de evidencia no son rangos de calidad. Un finding descriptivo tiene confianza
`NOT_ASSESSED`, un resultado de modelo es predictivo pero no causal. Una Wisdom
Card educativa no constituye una política aprendida y validada. Decision mantiene
`REVIEW_REQUIRED` y outcome `NOT_OBSERVED`; no ejecuta operaciones comerciales.

Cambio incompatible: incrementar versión mayor, añadir parser explícito y fixtures
de compatibilidad. Hasta entonces un cliente conserva su último pack válido.
No hay importación en Android implementada en esta entrega: este contrato y el
consumidor Python/HTML son la referencia para integrarla en `dntl_economia`.
