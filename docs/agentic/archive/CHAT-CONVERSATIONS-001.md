# Checkpoint previo: CHAT-CONVERSATIONS-001

Este checkpoint conserva el estado que estaba activo en main antes de iniciar MODEL-DATA-QUALITY-001.

# Active Task

Task ID: CHAT-CONVERSATIONS-001
Title: Importación y revisión programada de conversaciones comerciales
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/conversation-intelligence-manual
Base branch: main

## Result

El diagnóstico local del 12-oct-2026 confirma 25,421 mensajes, dos cargas y
reglas v2. Se añadió una tarea local de Windows con tres disparadores diarios
(09:00, 15:00, 21:00). Consulta PostgreSQL antes de cada intento y omite los
restantes del día de Lima después de una importación con new_messages > 0.
Las cargas sin mensajes nuevos y los errores no consumen el día. El TXT sigue
siendo privado y debe reemplazarse manualmente en conversaciones/.

## Validation

Cuatro pruebas aisladas del nuevo gate pasan; py_compile pasa. El export
diagnóstico acredita que la instalación SQL y el importador manual funcionaron
en el PostgreSQL local. El programador de tareas de Windows no se puede ejecutar
desde este entorno; requiere smoke test en el PC.

## Next action

En la rama, hacer git pull e instalar con
scripts/install_conversaciones_schedule.ps1. Revisar la tarea y ejecutar
scripts/check_conversaciones_scheduled.py una vez desde PowerShell. Ver
docs/conversaciones/PROGRAMACION.md.
