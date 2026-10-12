# Active Task

Task ID: CHAT-CONVERSATIONS-001
Title: Importación manual incremental de conversaciones comerciales
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/conversation-intelligence-manual
Base branch: main

## Result

La versión 2 de reglas vincula felicitaciones a separaciones anteriores hasta
24 horas con evidencia de asesor/proyecto/unidad, y cuenta visitas numéricas
sin exigir foto, sede o cierre de sesión. SQL añade vínculo y unidad; un nuevo
lanzador Windows importa y genera un ZIP privado completo de diagnóstico.

## Validation

Siete pruebas aisladas PASS; export privado de 25,421 mensajes procesado en
lectura (32 reportes candidatos de visitas, 421 separaciones y 2,318 reacciones
vinculadas). Prueba de ZIP con conexión simulada PASS. PostgreSQL local no
disponible aquí; migración SQL e importación pendiente de smoke test en el PC.

## Next action

Traer la rama del PR, ejecutar `scripts\\run_conversaciones_y_zip.bat` en el PC
y adjuntar el ZIP generado al siguiente chat para evaluar falsos positivos y
negativos con la evidencia completa.
