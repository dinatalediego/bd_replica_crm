# Active Task

Task ID: CHAT-CONVERSATIONS-001
Title: Importación manual incremental de conversaciones comerciales
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/conversation-intelligence-manual
Base branch: main

## Result

Parser de exportación WhatsApp, detección conservadora y versionada de eventos comerciales, contrato SQL append-only, vistas de visitas declaradas/ritmo/reacciones, integración solo con actualización manual y lanzador Windows. TXT excluido de Git.

## Validation

Cinco pruebas aisladas de parser, reglas, prefijo incremental y selección manual aprobadas con unittest. Export privado de 25,421 mensajes procesado en lectura, sin escribirlo en el repositorio. PostgreSQL local no disponible en este entorno; contrato SQL pendiente de smoke test en el PC.

## Next action

Revisar el PR y en el PC traer la rama, copiar el TXT a conversaciones/, ejecutar scripts\\run_conversaciones_manual.bat y revisar las vistas y reportes marcados para revisión. No unir automáticamente con métricas CRM sin conciliación.
