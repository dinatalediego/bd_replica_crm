# Tres intentos diarios para el TXT de ventas

La tarea de Windows revisa exclusivamente
`conversaciones/Chat de WhatsApp con Cygnus - Ventas.txt` a las 09:00, 15:00 y
21:00 de la zona horaria configurada en Windows. Puedes cambiar los tres horarios
al instalarla. La exportación de WhatsApp se copia manualmente a esa ruta; la tarea
no descarga ni sustituye el TXT por sí sola.

Cada intento consulta en PostgreSQL si **esta fuente** ya insertó al menos un
mensaje nuevo durante el día civil de `America/Lima`. En ese caso termina con
`SKIPPED_IMPORTED_TODAY`. Si todavía no ocurrió, ejecuta el importador normal:

- `UNCHANGED`: mismo archivo y versión de reglas; el siguiente horario vuelve a
  revisar.
- `IMPORTED` con `new_messages > 0`: se cargaron mensajes; los restantes
  horarios de ese día se omiten. Mañana se vuelve a revisar.
- `IMPORTED` con `new_messages = 0`: solo se reclasificaron reglas; el siguiente
  horario vuelve a revisar.
- `ERROR`: queda en el log con salida distinta de cero y se reintenta en el
  próximo horario. Si cambió el prefijo histórico, la importación se detiene
  antes de escribir y requiere conciliación manual.

La marca diaria proviene de `etl_control.conversation_import_runs` y sobrevive a
reinicios del PC. No se programan cambios de esquema ni se generan ZIP diarios;
`schema_sync --only conversaciones` se ejecuta una vez durante la instalación.
El proceso horario de Redshift permanece independiente.

## Instalar en PowerShell

Desde la raíz del repositorio, con `.venv` y el TXT ya preparados:

```powershell
git switch feat/conversation-intelligence-manual
git pull --ff-only origin feat/conversation-intelligence-manual
.\scripts\install_conversaciones_schedule.ps1
```

Si PowerShell restringe archivos descargados, ejecuta este instalador solo para
la sesión actual con:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_conversaciones_schedule.ps1
```

Para otros tres horarios (hora local del PC):

```powershell
.\scripts\install_conversaciones_schedule.ps1 -Hours 08:00,14:00,20:00
```

La tarea `Medallio - Conversaciones Cygnus Ventas` corre con el usuario que la
instaló, mientras tenga una sesión iniciada. Si el PC está apagado o dormido,
Windows intentará ejecutar la tarea al estar disponible; confirma ese
comportamiento en tu equipo. PostgreSQL debe estar iniciado y el TXT accesible.

## Verificar y operar

```powershell
Get-ScheduledTask -TaskName 'Medallio - Conversaciones Cygnus Ventas' |
    Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName 'Medallio - Conversaciones Cygnus Ventas' |
    Select-Object LastRunTime, LastTaskResult, NextRunTime
.\.venv\Scripts\python.exe .\scripts\check_conversaciones_scheduled.py
Get-Content .\conversaciones\scheduler_runs.jsonl -Tail 10
```

El comando de prueba respeta la misma regla diaria. Tras reemplazar el TXT,
espera el siguiente horario. Para una carga fuera del horario, usa
`.\scripts\run_conversaciones_manual.bat`; si inserta nuevos mensajes,
los intentos automáticos del resto del día se omitirán. Para producir un ZIP de
diagnóstico bajo demanda usa `.\scripts\run_conversaciones_y_zip.bat`.

La tarea no modifica el trabajo sucio de Git ni publica nombres o conversaciones.
El log queda ignorado por Git dentro de `conversaciones/`.
