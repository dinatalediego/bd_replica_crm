# Lead Scoring v0.2 — score → recomendación → acción → outcome

## Resultado

El loop de priorización ya no termina en una probabilidad. Cada score del modelo
`serving` se convierte de manera idempotente en una recomendación operativa; el
asesor o supervisor registra la acción humana y, cuando maduran los horizontes,
el sistema enlaza separación y minuta con la evidencia original.

```text
features.lead_evidence
  -> decision_intelligence.lead_scores
  -> decision_intelligence.recommendations
  -> decision_intelligence.actions
  -> decision_intelligence.outcomes
  -> v_lead_action_outcome_performance
```

## Semántica y límites

- La unidad de decisión es `evidence_key`: una asignación de lead en un momento.
- A/B/C/D es prioridad predictiva, no efecto causal.
- La recomendación nunca contacta automáticamente al cliente.
- `action_owner` es obligatorio para preservar responsabilidad humana.
- Una diferencia entre clientes contactados y no contactados es descriptiva;
  no demuestra todavía que el contacto causó la conversión.
- El scoring operativo excluye leads que ya registran separación o venta en el
  ciclo comercial certificado: una predicción solo es útil mientras la acción
  sigue siendo posible.
- Los outcomes negativos se observan al cerrar su horizonte; los positivos usan
  la primera fecha de evento certificada disponible.

## Acciones provisionales

| Banda | Acción recomendada |
|---|---|
| A | `CONTACTAR_PRIORIDAD_ALTA` |
| B | `CONTACTAR` |
| C | `NURTURE` |
| D | `NURTURE` |

Estas acciones son una política operativa inicial. Cambiarlas requiere una
decisión de negocio versionada, no reentrenar el predictor.

## Operación desde VS Code / PowerShell

Actualizar evidencia, score, recomendaciones y outcomes maduros:

```powershell
.\scripts\41_lead_scoring_live.bat
```

Consultar recomendaciones disponibles en PostgreSQL:

```sql
SELECT recommendation_id, lead_id, priority_band, priority_score,
       recommended_action, action_status
FROM decision_intelligence.v_lead_action_outcome
ORDER BY decision_date DESC, priority_score DESC;
```

Registrar lo que realmente hizo el equipo:

```powershell
python scripts/lead_scoring.py action `
  --recommendation-id "<UUID>" `
  --taken "CONTACTAR_PRIORIDAD_ALTA" `
  --owner "<usuario>" `
  --cost 0 `
  --notes "Contacto registrado por el supervisor"
```

Actualizar outcomes y medir:

```powershell
python scripts/lead_scoring.py outcomes
python scripts/lead_scoring.py measure
```

## Evidencia para Power BI

- `decision_intelligence.v_lead_action_outcome`: detalle por recomendación.
- `decision_intelligence.v_lead_action_outcome_performance`: cohortes por fecha,
  banda, estado de acción y acción tomada.

Antes de interpretar tasas, revisar `sep_matured` y `minuta_matured`. Una cohorte
sin horizonte maduro no debe compararse con cohortes completas.

## Demostración válida

El sistema demuestra el encadenamiento técnico cuando:

1. existe un `score_id` y una recomendación derivada;
2. la acción queda asociada al mismo `recommendation_id`;
3. separación/minuta quedan asociadas al mismo `evidence_key`;
4. Power BI muestra cobertura de acción y outcomes maduros;
5. puede reconstruirse modelo, versión, evidencia y fechas.

Esto demuestra trazabilidad y medición observacional. El efecto incremental se
demostrará en la fase 8 mediante asignación experimental o un diseño causal
aprobado.
