# Conversaciones comerciales en Medallio

Importa exportaciones TXT de WhatsApp que se reemplazan con el mismo nombre en
`conversaciones/`. Es una fuente local y privada; no añade consultas a Redshift.

## Uso en Windows

1. Exporta el chat **sin adjuntos**, conserva el nombre
   `Chat de WhatsApp con Cygnus - Ventas.txt` y cópialo a `conversaciones/`.
2. Ejecuta `scripts\run_conversaciones_manual.bat`. Instala el contrato SQL y
   carga solo mensajes nuevos. Si cambian las reglas, reclasifica el historial
   en una versión nueva sin duplicar los mensajes RAW.
3. Para preparar un ZIP completo para el siguiente chat, ejecuta
   `scripts\run_conversaciones_y_zip.bat` desde PowerShell. El archivo queda
   en `conversaciones\diagnostico_conversaciones_<fecha>.zip`; el lanzador
   incluye la carga anterior e imprime la ruta exacta.
4. Si usas `python scripts/dw_refresh.py --mode manual`, el paso de conversaciones
   se añade después de `schema_sync` cuando hay TXT en la carpeta. La tarea
   `--mode hourly` no incluye este paso.

Alternativa explícita: `python scripts/schema_sync.py --only conversaciones` y
después `python scripts/import_conversaciones.py --file "conversaciones/Chat de WhatsApp con Cygnus - Ventas.txt"`.
También se aceptan varios TXT de conversaciones distintas en la carpeta.

Si ya cargaste el TXT y solo quieres generar el ZIP:
`python scripts/export_conversaciones_diagnostico.py`. Para otra fuente usa
`--source-name "nombre-exacto.txt"`. El adjunto con sufijo `(1)` tiene el mismo
SHA-256 que el original; conserva el nombre original en `conversaciones/` para
que la nueva versión de reglas reclasifique la misma fuente.

El ZIP contiene todos los mensajes RAW (incluidos nombres y texto), todos los
eventos versionados, las vistas actuales, historial de cargas, contrato SQL y
un `manifest.json` con filas y SHA-256 por archivo. La ruta se ignora en Git.
Compártelo solo en el chat al que deseas entregar esa evidencia privada.

## Reglas de persistencia

- `etl_control.conversation_sources` guarda nombre, SHA-256 de la última versión,
  total de mensajes y versión de reglas. `conversation_import_runs` registra las
  cargas efectivas. Una versión idéntica devuelve `UNCHANGED`.
- `raw_conversations.messages` guarda cada mensaje y su posición original una
  sola vez. Se admiten mensajes repetidos literalmente; la posición ordinal los
  distingue. Hay un bloqueo de importación y una transacción por archivo.
- El export actualizado debe contener intacto el prefijo de mensajes ya cargado.
  Si cambió el historial o el archivo se recortó, la carga falla **antes de
  insertar**. No se suman dos veces las cifras de un mensaje editado. Conserva
  el TXT previo y revisa esas diferencias antes de hacer una reconciliación.
- `analytics.conversation_events` contiene hechos detectados por reglas. Una
  nueva versión de reglas crea otra versión de eventos; la vista `..._current`
  muestra solo la última. Los mensajes y eventos son inmutables. La versión 2
  vincula celebraciones a un anuncio anterior hecho por otra persona: hasta
  24 horas si menciona asesor/proyecto/unidad; una reacción genérica exige
  un único anuncio candidato dentro de 15 minutos. El vínculo se guarda en
  `related_event_id` y las asociaciones ambiguas se marcan para revisión.
- La fecha y hora del mensaje son hora local de Lima sin zona UTC en el export.
  `reported_date` usa "ayer" cuando aparece, y trata nombres de días como una
  inferencia marcada para revisión. `message_at` siempre conserva la hora del chat.

## Tablas y vistas

| Objeto | Grano | Uso |
| --- | --- | --- |
| `raw_conversations.messages` | mensaje original | Evidencia restringida, texto, remitente y línea |
| `analytics.conversation_events` | tipo detectado dentro del mensaje y versión de reglas | Separación, inicial, minuta, cita, visita, feria, salida, bloqueo, incidencia y reacción |
| `analytics.v_conversation_visit_reports` | cada cifra de visita explícita | Mínimo, máximo, sede, proyecto, fecha y revisión |
| `analytics.v_conversation_visits_daily` | fuente × fecha reportada × proyecto × sede | Suma de cifras reportadas y posible solapamiento |
| `analytics.v_conversation_project_hourly` | fuente × hora del mensaje × proyecto | Pulso operativo por hora |
| `analytics.v_conversation_project_day_signals` | fuente × fecha reportada × proyecto | Panel de señales comerciales |
| `analytics.v_conversation_daily_rhythm` | fuente × día × hora | Mensajes, autores y marcadores multimedia |
| `analytics.v_conversation_sale_reactions` | anuncio candidato de separación | Reacciones vinculadas hasta 24 horas, con desglose de los primeros 15 minutos |

```sql
SELECT * FROM analytics.v_conversation_visits_daily
WHERE venue_type IN ('sala', 'sala_inferida', 'feria')
ORDER BY reported_date DESC, project_name;

SELECT source_line, message_at, reported_date, project_name, venue_type,
       count_min, count_max, note
FROM analytics.v_conversation_visit_reports
WHERE review_required
ORDER BY message_at DESC;
```

Las visitas representan **cifras mencionadas en el chat**, no visitantes únicos
verificados. Dos personas pueden describir la misma afluencia; `potential_overlap`
advierte cuando hay varios reportes para el mismo grupo. `sala_inferida` proviene
de un mensaje que empieza por “Salida” y requiere revisión. Una cifra sin sede o
proyecto explícito queda sin atribuir, pero se conserva su número. Se reconocen
atenciones numéricas aunque no haya fotografía ni sede visible en el TXT. El
TXT omite el contenido de adjuntos;
`is_multimedia` mide presencia del marcador, no su contenido.

No se guarda el TXT en Git. El esquema RAW revoca acceso público. Antes de
confrontar estos eventos con separaciones/minutas del CRM, se requiere una regla
de enlace por proyecto/unidad/persona y una revisión de duplicados, fechas y
errores de extracción. No se usa el total de reacciones como conteo de visitas.
