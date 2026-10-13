# Active Task

Task ID: OPENAI-REVIEW-001
Title: Piloto de revisión de evidencia MEDALLIO con OpenAI
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: codex/medallio-ai-review-pilot-20261013
Base branch: main

## Result

Adaptador manual de Responses API para paquetes agregados v2.9.0, salida estructurada,
validación de referencias, borradores aislados y feedback humano. El esquema SQL es optativo
y está excluido de la sincronización desatendida. Ver `docs/ai_review_pilot.md`.

## Validation

`PYTHONPATH=src python tests/test_ai_review.py`: cinco pruebas sintéticas aprobadas.
`python -m py_compile` de los tres módulos cambiados: aprobado.
No se usaron datos reales, clave API ni PostgreSQL en esta revisión.

## Next action

Revisar el PR borrador. Un responsable de datos debe aprobar el paquete agregado y los
ajustes de retención/costo antes de una llamada real. Ejecutar un solo piloto manual en
entorno autorizado y calificar cada hallazgo; integrar únicamente tras la evaluación.

