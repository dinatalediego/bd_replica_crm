# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL 1.0
Task: CHAT-CONVERSATIONS-001 — Importación y revisión programada
From: chatgpt
To: human
Status: REVIEW_READY
Branch: feat/conversation-intelligence-manual
Checkpoint code commit: df259a162fd6696b14195db03957114d80dae344

## Exact next action

Traer la rama, instalar `scripts/install_conversaciones_schedule.ps1` en
PowerShell y ejecutar `scripts/check_conversaciones_scheduled.py` una vez.
Ver `docs/conversaciones/PROGRAMACION.md` para horarios, requisitos y log.

## Evidence

El diagnóstico privado del usuario contiene 25,421 mensajes, 2 corridas,
la segunda con 0 mensajes nuevos y 2,935 eventos reclasificados. El código
de programación consulta `new_messages > 0` para cortar intentos solo
después de una verdadera ampliación del TXT en el día civil de Lima.

Cuatro pruebas aisladas de programación y `py_compile` pasaron. La tarea
de Windows no pudo ejecutarse aquí; el smoke test local sigue pendiente.
No se incluyeron TXT ni JSONL privados en Git.
