# Medallio Ambassador v2.7 — Evidence & Outcome Gate

## Qué agrega

v2.7 cierra la brecha entre **"Medallio recomienda"** y **"Medallio demuestra valor"**.

La arquitectura nueva es:

```text
HECHO OBSERVADO
    ↓ gate
DIAGNÓSTICO
    ↓ gate
PREDICCIÓN
    ↓ gate
RECOMENDACIÓN
    ↓ gate
DECISIÓN ECONÓMICA
    ↓ gate
APRENDIZAJE CAUSAL
    ↓ gate
CLOSED-LOOP GROWTH
```

Cada nivel puede quedar:

- `PASS`
- `WARN`
- `BLOCK`

Un nivel superior no se considera validado si el anterior está bloqueado.

## Por qué esto importa

Ejemplo:

```text
Coverage = 100%
WAPE = N/A
Trust = 50%
```

Medallio puede tener reporting y diagnóstico fuertes, pero el gate predictivo
debe permanecer `BLOCK` hasta medir error y confianza suficientes.

Eso evita decir "AI madura" sólo porque existe un modelo.

## Nuevos artifacts

```text
artifacts\medallio_ceo_briefing\
    evidence_gate_register.csv
    evidence_outcome_summary.json
    project_growth_state.csv
    decision_ledger_candidate.csv
    decision_outcome_gap.csv
```

## Objetos PostgreSQL

La migración crea:

```text
analytics.project_growth_state_snapshot
analytics.v_project_growth_state

decision_intelligence.decision_ledger
decision_intelligence.action_log
decision_intelligence.outcome_ledger
decision_intelligence.v_decision_outcome_status

experiments.baseline_challenger

model_control.evidence_gate
model_control.v_evidence_gate_current
```

## Modelo de decisión

### decision_ledger
Qué se recomendó / decidió:
- proyecto
- owner
- rationale
- deadline
- Value at Risk
- Value to Capture
- Action Cost
- Confidence
- Expected ROI

### action_log
Qué se hizo realmente.

### outcome_ledger
Qué ocurrió después:
- baseline
- observed
- incremental
- value_realized
- attribution_method
- maturity_status

### baseline_challenger
Cómo separar correlación de causalidad.

## D0 → D3

v2.7 deja preparado este marco:

```text
D0 = informar
D1 = recomendar
D2 = ejecutar con aprobación humana
D3 = ejecución autónoma
```

El Ambassador crea candidatos en D1.
No promueve automáticamente una decisión económica a D2/D3.

## Google Sheets

Se agregan automáticamente:

```text
EVIDENCE_GATES
DECISION_OUTCOME
```

## Slides

La última slide del briefing ahora es:

```text
Evidence & Outcome Gate · disciplina antes de escalar
```

No muestra sólo "qué hacer".
Expone qué afirmaciones están soportadas, cuáles están bloqueadas y qué evidencia falta.

## Instalación

Copia/reemplaza los archivos del ZIP dentro de:

```text
C:\Projects\bd_replica_crm
```

Primero valida sin tocar PostgreSQL:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_v27.ps1
```

Luego prueba:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Deberías ver algo tipo:

```text
V2.7 | altitude=L2 Diagnóstico & Comparabilidad |
next=PREDICTIVE BLOCK
```

Si todo se ve correcto, instala la capa persistente:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_v27.ps1 -ApplySchema
```

Después añade al `config\medallio_ambassador_v2.json`:

```json
"v27": {
  "auto_sync_db": true
}
```

y ejecuta:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Qué deberías esperar inicialmente

Con un briefing donde WAPE todavía es `N/A`, v2.7 debería impedir que la dimensión
predictiva aparezca como madura.

Eso es correcto.

El objetivo ya no es que todos los gates estén verdes.
El objetivo es que **cada gate verde pueda defenderse ante Gerencia, Finanzas o un cliente**.
