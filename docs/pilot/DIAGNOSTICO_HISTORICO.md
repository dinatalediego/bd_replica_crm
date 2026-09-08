# Diagnóstico histórico de solo lectura

Objetivo: preparar la decisión de proyectos, tasa base y flujo de captación para el piloto. No requiere registrar ni activar un experimento, ni cambiar el notebook a LIVE.

Desde la raíz del repositorio en PowerShell:

```powershell
.\scripts\47_lead_pilot_history.bat
```

Usa 180 días completos hasta ayer, calendario de Lima. Opcional:

```powershell
.\scripts\47_lead_pilot_history.bat --days 365
.\scripts\47_lead_pilot_history.bat --days 180 --end 2026-09-07
```

`--end` es exclusivo; no incluye el día indicado. La consulta tiene timeout de 60 segundos. Si falla, compartir el error y no lanzar backfills ni entrenamientos para solucionarlo.

Lee solo `features.lead_evidence` en transacción REPEATABLE READ / READ ONLY. No crea tablas, índices o vistas, no actualiza etiquetas, no consulta Redshift y no modifica el piloto. Utiliza la configuración local existente del repositorio. Los únicos archivos escritos son agregados en una carpeta nueva `reports/pilot_history/<fecha_uuid>/`, excluida de Git:

- `RESUMEN.md`: tabla por proyecto y conciliación.
- `diagnostico.json`: indicadores completos y serie diaria con ceros. Adjuntar este archivo para el análisis; no contiene documentos ni teléfonos, pero sí métricas comerciales internas.

## Cómo interpretar

`assignments` cuenta evidencias/asignaciones; `first_client_project` cuenta primera aparición observada del cliente por proyecto en toda la historia disponible antes de seleccionar la ventana. `repeat_assignments` es la diferencia. El mismo cliente puede estar en varios proyectos. `first_client_global` lo atribuye exclusivamente al primer proyecto observado (desempate estable por evidence_key); no equivale a conversión global por cualquier proyecto.

El flujo usa todos los días calendario, incluidos ceros. La referencia reciente usa hasta 28 días. Un cero puede ser ausencia real de leads o un problema de cobertura ETL; contrastar fechas de actividad y aperturas/cierres del proyecto.

Las conversiones de separación/minuta usan las etiquetas ya almacenadas de la primera aparición cliente/proyecto. Se exige fecha de maduración y `labels_as_of` suficiente. Maduros sin etiqueta válida se reportan como faltantes. La tasa de cohorte completa se deja nula cuando hay faltantes; la tasa observada y sus intervalos no solucionan ese sesgo. Se incluyen límites extremos para los resultados faltantes.

`source_rows = valid_rows + invalid_identity_or_project` concilia el conjunto de evidencia de la ventana y los agregados. Los rechazados son identidades/proyectos vacíos; se reportan por conteo, sin exportar datos personales. Evidencias después del corte se informan aparte. No es certificación de réplica Redshift ni comparación con procesos.

## Lo que falta antes de usar BASE_RATE / ELIGIBLE_PER_DAY

1. Verificar que los horizontes actuales siguen siendo separación 14 días y minuta 60, así como zona horaria y reglas de procesos/caídas.
2. Elegir proyectos y revisar cobertura, mezcla LIVE/BACKFILL, faltantes y número de positivos.
3. Aprobar elegibilidad (consentimiento, compra previa, nuevos/recurrentes) y umbral del modelo. Este diagnóstico no aplica esas exclusiones: flujo observado no es todavía flujo elegible.
4. Estimar la tasa y flujo del subconjunto aprobado. No aplicar un porcentaje arbitrario de elegibilidad.
5. Acordar MDE comercial; después calcular potencia/muestra y plazo. El diagnóstico no fija un MDE ni promete resultados o duración.

La ausencia de conexión desde este entorno al DW de Windows impide emitir cifras reales aquí. La ejecución local y el JSON son la evidencia necesaria. No compartir `.env`, claves ni extractos de clientes.

## Pruebas

`tests/test_pilot_history.py`: días cero, faltantes, conciliación, ventana y límites.
`tests/test_pilot_history_postgres.py`: SQL real con cliente anterior a ventana, reasignaciones, cliente multiproyecto, identidad inválida, madurez incompleta y corte exclusivo. Usa la misma base vacía de pruebas indicada en `VERIFICACION.md`; no la operativa.

Verificación del 2026-09-08: dos pruebas de resumen Python pasaron; también pasaron la prueba SQL histórica y la regresión del ciclo experimental sobre PostgreSQL/WASM aislado. En la prueba histórica: 5 evidencias en la ventana = 4 válidas agregadas + 1 identidad rechazada; una fila en el límite final quedó excluida. El cliente presente antes de la ventana no se contó como nuevo al reasignarse. El número de filas de origen permaneció igual antes y después de la consulta. No se han obtenido aún métricas reales del DW del usuario.
