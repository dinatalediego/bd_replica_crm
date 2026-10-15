# Medallio v2.7.1 — Evidence Calibration Hotfix

Este hotfix corrige exactamente cuatro problemas detectados en los outputs CEO.

## 1. Readiness / Heatmap ahora consumen Evidence Gates

Antes:
- existencia de objetos / contratos / capacidades podía producir 100%.

Ahora:
- `00_ceo_layer_readiness.png` = madurez **secuencial validada**;
- `09_ceo_heatmap.png` = estado **local de cada gate**.

Escala:
- PASS = 100
- WARN = 50
- BLOCK = 0

La altitud secuencial no permite saltar un gate bloqueado.

## 2. L6 causal ya no pasa por nombres de columnas

Antes:
- encontrar palabras como `treatment`, `control`, `outcome` podía activar causalidad.

Ahora L6 PASS requiere al menos una fila real con:
- treatment,
- control/challenger,
- baseline,
- observed outcome,
- outcome `MATURE`,
- vínculo completo experimento → outcome.

Si existe sólo parte de la evidencia:
- WARN.

Sin filas reales:
- BLOCK.

## 3. Forecast excluye meses incompletos

El WAPE de Evidence Gate se recalcula sólo con periodos maduros.

Orden:
1. si existe `mature_for_evaluation` / `period_complete`, se respeta;
2. si no existe, se excluye el mes calendario actual;
3. si no hay periodo ni flag, la fila NO se considera madura.

Nuevo artifact:

```text
forecast_evaluation_maturity.csv
```

y el summary guarda:
- mature_rows,
- immature_rows_excluded,
- mature_wape_pct.

## 4. Value at Stake desaparece si es ilustrativo

`01_value_at_stake*.png` se elimina si no hay al menos una decisión con:

```text
quantification_status = quantified
value_to_capture != null
```

No se reemplaza por escenarios ficticios.

Se crea:

```text
value_at_stake_status.json
```

para dejar trazabilidad de por qué el gráfico fue suprimido.

## Nuevos artifacts

```text
forecast_evaluation_maturity.csv
causal_evidence_status.json
value_at_stake_status.json
```

## Instalación

Reemplaza dentro de `C:\Projects\bd_replica_crm`:

```text
scripts\medallio_evidence_outcome_v27.py
scripts\rebuild_v271_ceo_visuals.py
```

`medallio_ambassador_v2.py` se mantiene compatible con la v2.7.

Valida:

```powershell
python -m py_compile .\scripts\medallio_evidence_outcome_v27.py
python -m py_compile .\scripts\medallio_ambassador_v2.py
```

Prueba:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

Resultado esperado con el estado observado actual:

```text
L1 Observed       PASS
L2 Diagnostic     WARN
L3 Predictive     BLOCK
L4 Recommendation PASS
L5 Economics      BLOCK
L6 Causal         BLOCK
L7 Closed Loop    BLOCK

Growth Altitude: L1
```

Hasta que L2 y L3 se validen, Readiness ya no mostrará capas superiores como 100% maduras.

## Recalibrar sólo gráficos

Después de una corrida v2.7.1:

```powershell
python .\scripts\rebuild_v271_ceo_visuals.py
```
