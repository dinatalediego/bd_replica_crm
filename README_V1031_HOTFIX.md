# v1.0.3.1 Hotfix

## Error corregido

PostgreSQL reportaba:

```text
DuplicateColumn: la columna «model_name» fue especificada más de una vez
```

La causa estaba en:

```text
analytics.v_forecast_evaluation_candidate_v103
```

`mc.*` ya incluía:

```text
model_name
model_version
model_family
```

porque `analytics.v_forecast_monthly_maturity_clock_v102` hereda esas columnas
de `analytics.v_forecast_monthly_current_v102`.

v1.0.3 intentaba volver a agregarlas desde `forecast_model_registry_v1`.

El hotfix deja:

```text
mc.*
r.model_version_id
sample_rank
```

sin duplicar columnas.

## Por qué `status` fallaba después

La instalación v1.0.3 corre dentro de una transacción SQL. Al fallar la creación
de la vista, PostgreSQL hizo rollback de esa instalación. Por eso luego:

```text
analytics.v_forecast_ceo_evidence_status_v103
```

todavía no existía.

## Instalar

Descomprime este paquete sobre `bd_replica_crm` y ejecuta:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\89_install_forecast_factory_v1031_hotfix.ps1
```

También puedes volver a ejecutar directamente:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\86_install_forecast_factory_v103.ps1
```

después de reemplazar el SQL corregido.

## Resultado esperado ahora

Dado el estado v1.0.2 mostrado antes, es razonable que el primer estado sea:

```text
evaluated prospective pairs = 0
next evidence unlock = 2026-12-01
scoreboard = empty
champion = NOT_YET_DECLARED
```

Eso es correcto: v1.0.3 no debe fabricar evidencia antes de que maduren los
outcomes.
