# Modelo semántico recomendado — Medallio Control Tower

Renombra las consultas de Power Query así:

| Consulta M | Nombre en el modelo |
|---|---|
| qDimAsset | Dim Asset |
| qDimDate | Dim Date |
| qAssetHealthCurrent | Asset Health Current |
| qAssetQualityCurrent | Asset Quality Current |
| qAssetSnapshots | Asset Snapshots |
| qPipelineRuns | Pipeline Runs |
| qQualityChecks | Quality Checks |
| qModelHealthCurrent | Model Health Current |
| qDecisionHealthDaily | Decision Health Daily |

## Relaciones

1. `Dim Asset[asset_key]` 1 → * `Pipeline Runs[asset_key]`
2. `Dim Asset[asset_key]` 1 → * `Asset Snapshots[asset_key]`
3. `Dim Asset[asset_key]` 1 → * `Quality Checks[asset_key]`
4. `Dim Asset[asset_key]` 1 → 1 `Asset Health Current[asset_key]` (Power BI puede materializarlo como 1:*; filtro simple desde Dim Asset)
5. `Dim Asset[asset_key]` 1 → 1 `Asset Quality Current[asset_key]`
6. `Dim Date[Date]` 1 → * `Pipeline Runs[run_date]`
7. `Dim Date[Date]` 1 → * `Asset Snapshots[snapshot_date]`
8. `Dim Date[Date]` 1 → * `Quality Checks[check_date]`
9. `Dim Date[Date]` 1 → * `Decision Health Daily[decision_date]`

Dirección de filtro recomendada: **Single**, desde dimensiones hacia hechos.

`Model Health Current` queda desconectada en Sprint 1 porque es una tabla de estado actual. Cuando exista historial de métricas se recomienda crear `Dim Model` y `Fact Model Run`.

## Diagrama

```text
                         ┌─────────────────┐
                         │    Dim Asset    │
                         │    asset_key    │
                         └───────┬─────────┘
                                 │ 1
                ┌────────────────┼──────────────────────┐
                │                │                      │
                ▼ *              ▼ *                    ▼ *
      ┌────────────────┐ ┌────────────────┐   ┌────────────────┐
      │ Pipeline Runs  │ │Asset Snapshots │   │ Quality Checks │
      └───────┬────────┘ └───────┬────────┘   └───────┬────────┘
              │                  │                    │
              └──────────────────┼────────────────────┘
                                 │ *
                                 ▼ 1
                         ┌─────────────────┐
                         │    Dim Date     │
                         └─────────────────┘

Dim Asset ──> Asset Health Current
Dim Asset ──> Asset Quality Current

Dim Date ──> Decision Health Daily
Model Health Current (estado actual, sin relación en Sprint 1)
```

## Grano de cada tabla

- **Pipeline Runs:** una fila por ejecución de una tabla.
- **Asset Snapshots:** una fila por activo por captura de observabilidad.
- **Quality Checks:** una fila por check ejecutado dentro de un snapshot.
- **Asset Health Current:** una fila por activo con último estado operacional.
- **Asset Quality Current:** una fila por activo con último control profundo.
- **Model Health Current:** una fila por modelo/sistema de decisión más reciente.
- **Decision Health Daily:** una fila por día y sistema de decisión.

Mantener estos granos explícitos evita dobles conteos en DAX.
