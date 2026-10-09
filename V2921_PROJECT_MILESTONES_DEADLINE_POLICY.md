# Medallio v2.9.2.1 — Project Milestones + Deadline Policy

## Fechas incorporadas

Todas se preservan como **PRELIMINARY**, exactamente como fueron entregadas:

| Proyecto | Código | Fecha preliminar |
|---|---|---|
| Tizón y Bueno | TZ | 2025-12-30 |
| Edificio Urbanzen | EEUU | 2025-06-30 |
| Alicanto | GY | 2026-11-30 |
| Capadocia | CP | 2026-09-30 |
| Sialia | SL | 2026-12-30 |
| Fenix | FX | 2026-06-30 |
| Modena | MD | 2027-09-30 |
| Matera | MT | 2027-09-30 |
| Torre Nápoles | NP | 2028-11-30 |

Una fecha preliminar pasada **no** se interpreta como entrega real.

## Configs incluidos

```text
config/project_milestones_v2921.json
config/deadline_policy_v2921.json
config/contract_routes_v292.json
config/contract_measurement_defaults_v2921.json
config/deadline_recommendations_reference_2026_10_08.json
```

## Bandas de timing

```text
PAST_PRELIMINARY_DATE   fecha preliminar ya pasó
CRITICAL                0–30 días
LATE                    31–90 días
MID                     91–180 días
EARLY                   >180 días
```

## Referencia al 2026-10-08

```text
MD  357 días  EARLY  → approval deadline recomendado: 2026-10-29
MT  357 días  EARLY  → approval deadline recomendado: 2026-10-29

CP   -8 días  PAST_PRELIMINARY_DATE
    → design deadline recomendado: 2026-10-13
    → revisar primero el status real del milestone

NP  784 días  EARLY
    → reconciliation deadline recomendado: 2026-10-15

SL   83 días  LATE
    → evidence review deadline recomendado: 2026-10-15
```

Los deadlines son **recomendaciones**, no compromisos aprobados.

## Outcome windows

Default según runway:

```text
EARLY     90 días
MID       60 días
LATE      30 días
CRITICAL  14 días
PAST      30 días, pero nuevos experimentos quedan bloqueados hasta revisar status
```

## Instalación

Requiere v2.9.2 previamente instalado.

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts9_install_project_milestones_deadline_policy.ps1
```

## Qué hará

1. Guarda las nueve fechas en `analytics.project_milestone_v2921`.
2. Calcula distancia a entrega y banda temporal.
3. Genera una recomendación de deadline según la ruta del proyecto.
4. Enriquece los `approval_template.json` de MD y MT.
5. **No completa ni aprueba silenciosamente campos humanos.**

## MD / MT approval template

Después de instalar encontrarás dentro del template:

```json
"recommendations_v2921": {
  "recommended_deadline": "2026-10-29",
  "recommended_outcome_window_days": 90,
  "primary_metric_recommendation": "absorcion_promedio_3m",
  "...": "..."
}
```

Los campos reales seguirán como:

```json
"deadline": null,
"success_criterion": null,
"outcome_window_days": null,
"approved_by": null
```

Esto es intencional.

Si aceptas una recomendación, la copias al campo real y defines un criterio de éxito
numérico antes de ejecutar `approve`.

## Guardrail importante

Para una fecha preliminar pasada:

```text
PAST_PRELIMINARY_DATE != DELIVERED
```

Medallio exige revisar el status real antes de usar la fecha para autorizar un nuevo experimento.

## Objetos SQL

```text
analytics.project_milestone_v2921
analytics.v_project_schedule_context_v2921

decision_intelligence.project_deadline_recommendation_v2921
decision_intelligence.v_project_deadline_recommendation_latest_v2921
```
