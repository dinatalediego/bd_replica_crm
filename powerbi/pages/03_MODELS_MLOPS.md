# Página 03 — Models & MLOps

## Pregunta ejecutiva
**¿Los modelos están actualizados, usando features recientes y comportándose como se espera?**

Esta página queda preparada desde Sprint 1 y empezará a poblarse cuando registres `model_control.model_runs` y `model_control.scoring_batches`.

## Fila 1 — KPIs
1. `Estado Global Modelos`
2. `Modelos Registrados`
3. `Último Entrenamiento`
4. `Último Scoring`
5. `Modelos con Drift`
6. `Feature Freshness Máx (min)`

## Fila 2
Tabla por modelo:
- decision_system
- model_name
- model_version
- trained_at
- last_scored_at
- data_as_of
- feature_freshness_minutes
- drift_score
- drift_status
- training_status
- scoring_status

## Fila 3 — Métrica adecuada por problema
No mezclar métricas sin contexto:
- clasificación: ROC-AUC, PR-AUC, Brier, calibration
- forecast: MAE, WAPE/MAPE, bias, cobertura de intervalos
- causal/uplift: ATE/CATE, AUUC/Qini, intervalos de confianza

## Regla de negocio
Un modelo puede tener buen AUC y seguir siendo inútil si sus features están viejas o si la decisión que activa no genera valor incremental.
