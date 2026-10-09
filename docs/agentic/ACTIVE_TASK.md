# Active Task

Task ID: ATLAS-PUBLISH-001
Title: Productos analíticos portables y evidencia para Atlas
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/atlas-analytical-products
Base branch: main

## Result

Implementación aditiva de los 12 puntos aprobados: data/model/story/scenario packs,
fábrica baseline, Findings, DecisionInsight, Wisdom Cards, registro publish y
feedback privado append-only. Demo sintética y consumidor HTML offline.

## Validation

Ver docs/publishing/VALIDATION.md para comandos, resultados y límites.
No hay acceso al PostgreSQL del usuario ni importador Android implementado aquí.

## Next action

Publicar e integrar el PR autorizado; en el PC ejecutar schema_sync --only publishing
y probar capture/build/register con datos locales. La réplica horaria no cambia.
