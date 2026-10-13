# Active Task

Task ID: OPENAI-REVIEW-001
Title: Data Partner: revisión OpenAI y mart mínimo en Supabase
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: codex/medallio-ai-review-pilot-20261013
Base branch: main

## Result

Adaptador manual de Responses API para paquetes agregados v2.9.0, salida estructurada,
validación de referencias, borradores aislados y feedback humano. Se añadió un mart
privado proyecto-mes en Supabase con referencia HMAC y vista de pares de entrenamiento.
Ambos esquemas son optativos y están fuera de la sincronización desatendida.
Ver `docs/ai_review_pilot.md` y `docs/SUPABASE_MINIMAL_MART.md`.

## Validation

`PYTHONPATH=src python tests/test_ai_review.py`: cinco pruebas sintéticas aprobadas.
`PYTHONPATH=src python tests/test_supabase_mart.py`: cuatro pruebas sintéticas aprobadas.
`python -m py_compile` de los módulos del piloto: aprobado.
Supabase: 24 meses sintéticos, 22 pares, cero errores de stock, RLS activo y sin acceso `anon`.
No se usaron datos reales ni clave API. No se ejecutó el exportador contra PostgreSQL local.

## Next action

Revisar el PR borrador. Un responsable de datos debe aprobar los paquetes agregados,
la región y el tratamiento en Supabase y los ajustes de retención/costo en OpenAI.
Ejecutar una carga y una revisión manuales en entorno autorizado; calificar cada hallazgo.

