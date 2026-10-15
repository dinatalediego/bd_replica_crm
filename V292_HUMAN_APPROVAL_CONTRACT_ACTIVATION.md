# Medallio v2.9.2 — Human Approval + Contract Activation + Outcome SLA

## Objetivo

Cerrar la distancia entre:

```text
AI recommendation
→ human approval
→ frozen contract
→ action
→ outcome SLA
→ mature outcome
→ learning
```

sin permitir que la IA active decisiones por sí sola.

## Routing explícito de esta fase

```text
MD  → ACTIVATION_CANDIDATE
MT  → ACTIVATION_CANDIDATE

CP  → DESIGN_ONLY
NP  → BLOCKED_RECONCILIATION
SL  → EVIDENCE_BUILDING
```

La instalación NO aprueba ni activa MD/MT.

## Máquina de estados

```text
DRAFT_REVIEW_REQUIRED
        ↓ human approval
APPROVED_READY
        ↓ explicit activation
ACTIVE
        ↓
WAITING_OUTCOME
        ↓
OUTCOME_MATURE
        ↓
LEARNING_COMPLETE
```

Salidas posibles:

```text
REJECTED
CANCELLED
```

## Objetos SQL

```text
decision_intelligence.project_contract_route_v292
decision_intelligence.project_contract_approval_v292
decision_intelligence.project_active_contract_v292
decision_intelligence.project_contract_outcome_v292
decision_intelligence.project_contract_event_v292

decision_intelligence.v_contract_activation_readiness_v292
decision_intelligence.v_outcome_sla_v292
analytics.v_contract_command_center_v292
```

## Baseline y diseño congelados

Al activar el contrato quedan protegidos por trigger:

```text
owner
deadline
primary_metric
baseline
success_criterion
outcome_window_days
action_cost
outcome_capture_method
ROI measurement plan
```

No se pueden editar después.

Si el diseño cambia:

```text
CANCEL → new draft → new approval → new contract
```

Esto evita reescribir la hipótesis después de observar resultados.

## Instalación

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\78_install_human_approval_contract_activation.ps1
```

La instalación genera:

```text
artifacts/contract_activation_v292/MD/approval_template.json
artifacts/contract_activation_v292/MT/approval_template.json

artifacts/contract_activation_v292/CP/route_status.json
artifacts/contract_activation_v292/NP/route_status.json
artifacts/contract_activation_v292/SL/route_status.json
```

## 1. Human approval — MD

Abrir:

```text
artifacts/contract_activation_v292/MD/approval_template.json
```

Completar manualmente:

```text
owner_confirmed
deadline
success_criterion
outcome_window_days
outcome_capture_method
action_cost
roi_measurement_plan
approved_by
```

No cambies el baseline para "mejorarlo".
Si el baseline ya está obsoleto, genera un nuevo draft/contexto.

Aprobar:

```powershell
python .\scripts\contract_activation_v292.py approve `
  --file .\artifacts\contract_activation_v292\MD\approval_template.json
```

Debe terminar en:

```text
MD APPROVED_READY
```

## 2. Activate — sólo después de approval

```powershell
python .\scripts\contract_activation_v292.py activate `
  --project MD `
  --actor "Diego"
```

El contrato pasa a:

```text
ACTIVE
```

y calcula:

```text
outcome_due_date = activation_date + outcome_window_days
```

## 3. Record interim/final outcome

Ejemplo:

```powershell
python .\scripts\contract_activation_v292.py record-outcome `
  --project MD `
  --actor "Diego" `
  --metric-value 6.2 `
  --value-realized 250000 `
  --source-reference "analytics.comercial_proyecto_mes" `
  --evidence-note "Cierre validado del periodo."
```

Si todavía no llegó `outcome_due_date`:

```text
WAITING_OUTCOME / OUTCOME_IMMATURE
```

Si el outcome fue observado en o después de la fecha de madurez:

```text
OUTCOME_MATURE
```

## 4. Complete learning

Sólo existe si hay al menos un outcome maduro:

```powershell
python .\scripts\contract_activation_v292.py complete-learning `
  --project MD `
  --actor "Diego" `
  --summary "La intervención..."
```

Entonces:

```text
LEARNING_COMPLETE
```

## Outcome SLA

`decision_intelligence.v_outcome_sla_v292` distingue:

```text
WAITING_OUTCOME
OUTCOME_IMMATURE
OUTCOME_MATURE
EXECUTION_DEADLINE_BREACH
OUTCOME_SLA_BREACH
LEARNING_COMPLETE
```

## CP / NP / SL

### CP
```text
DESIGN_ONLY
```
Puede seguir produciendo Value to Capture y diseños de intervención,
pero v2.9.2 rechazará `approve`.

### NP
```text
BLOCKED_RECONCILIATION
```
No puede aprobarse hasta resolver el gate económico.

### SL
```text
EVIDENCE_BUILDING
```
No puede aprobarse para intervención. Debe seguir ampliando
diagnóstico y evidencia prospectiva.

## Artifacts

```text
artifacts/contract_activation_v292/
    contract_command_center.md
    contract_command_center.csv
    outcome_sla.csv
    11_contract_activation_routes.png
```

## Regla de gobierno

```text
AI proposes
→ evidence constrains
→ human approves
→ system freezes
→ business acts
→ outcome judges
→ Medallio learns
```

No se crea ningún claim causal automáticamente.
