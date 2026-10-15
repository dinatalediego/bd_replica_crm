# Medallio → productos analíticos portables

Esta capa implementa la dirección de los 12 puntos aprobados con una experiencia
completa, pequeña y reproducible. La réplica sigue siendo responsable de traer
los datos. `publishing` transforma un agregado conciliado en datos, un baseline,
evidencia, escenarios, una decisión por revisar, una historia y una enseñanza.

## Ejecutar la demostración sin base de datos

Desde la raíz del repositorio, con Python 3.11 o 3.12:

```powershell
python -m pip install -e ".[publishing]"
$commit = git rev-parse HEAD
python scripts/publish_atlas.py demo --output artifacts/atlas/demo.zip --generated-at 2026-10-09T18:00:00Z --git-commit $commit
python scripts/publish_atlas.py validate artifacts/atlas/demo.zip
python scripts/publish_atlas.py preview artifacts/atlas/demo.zip --output artifacts/atlas/demo.html
Start-Process artifacts/atlas/demo.html
```

La demo contiene dos proyectos ficticios, nueve meses y un inventario fijo.
Nunca lee el CRM, variables de conexión, archivos `.env` ni resultados privados.
Su etiqueta permanente es **DEMO / SYNTHETIC DATA**. La demo no es evidencia del
rendimiento real de Cygnus ni de un modelo entrenado en Medallio.

La vista HTML es un consumidor de referencia: muestra indicadores, gráfico,
tabla, Model Card, evidencia, multiplicador de ritmo, escenario original y límites.
Todo funciona offline. El importador nativo está propuesto en el PR draft de Atlas Android #15; la compilación/firma 0.3.0 y prueba visual siguen pendientes.

## Conectar tu PostgreSQL local

Requisitos: `analytics.comercial_proyecto_mes` instalado y actualizado por el flujo
existente de evolución comercial; meses consecutivos completos; sin unidades en
revisión; cohorte fija y al menos siete meses por proyecto. El adaptador hereda las
reglas NP-A y ventas vigentes del contrato existente. No añade filtros sobre RAW.

Instalar **solo** el nuevo registro, sin alterar pipelines:

```powershell
python scripts/schema_sync.py --only publishing
```

Para inspeccionar: `python scripts/schema_sync.py --only publishing --status`. No habilitar todas las migraciones para esta funcionalidad.

Establecer `MEDALLIO_PUBLISH_DSN` únicamente en el entorno local por el mecanismo
habitual de credenciales. No pegar su valor en Git, documentación, packs ni chats.
Los comandos de publicación no necesitan credenciales de Redshift.

```powershell
python scripts/publish_atlas.py capture --as-of 2026-10-09 --output artifacts/atlas/private-snapshot.json
$commit = git rev-parse HEAD
python scripts/publish_atlas.py build --snapshot artifacts/atlas/private-snapshot.json --output artifacts/atlas/private.zip --generated-at 2026-10-09T18:00:00Z --git-commit $commit
python scripts/publish_atlas.py validate artifacts/atlas/private.zip
python scripts/publish_atlas.py preview artifacts/atlas/private.zip --output artifacts/atlas/private.html
```

`capture` lee exclusivamente seis columnas agregadas de una tabla local en una
transacción de solo lectura, con timeout y máximo de 10.000 filas. No ejecuta
refreshes ni cambia el ciclo horario. No reconstruye información conocida en el
pasado: `as_of` limita los períodos pero la historia sigue siendo revisada.
Si falla calidad o cobertura, el producto completo se rechaza; no se descartan
proyectos silenciosamente. Corregir la fuente o preparar otro producto con un
contrato explícito. La primera versión no admite cohortes con reposiciones.

Para consumo en Android, compila Atlas 0.3.0 desde su rama/PR con la misma clave
privada que firma la instalación; la app 0.2.0 existente no incluye este lector.
Copia únicamente `artifacts/atlas/private.zip` por un canal local al teléfono,
abre **Productos → Importar pack Atlas** y selecciónalo desde el selector de
archivos. El pack se conserva en almacenamiento privado de la app. No subir el ZIP
a Git, no incluirlo en el ZIP/APK de instalación y no pegar el DSN en comandos
compartidos. La demo sintética no es un sustituto de este pack privado.

Los snapshots, ZIP y HTML reales son **PRIVATE**, incluso siendo agregados.
`artifacts/` ya está ignorado por Git. Anonimizar el código del proyecto no convierte
el archivo en público. La salida pública incluida en este cambio se deriva solo
de la fixture fija; no existe exportación pública automática de CRM.

## Uso en Power BI y Medallio OS

`publish.data_product`, `publish.indicator`, `publish.model_run`,
`publish.model_metric`, `publish.model_prediction`, `publish.scenario`,
`publish.finding`, `publish.numeric_story`, `publish.decision_insight` y
`publish.wisdom_card` exponen JSONB de releases registrados. Filtrar siempre por
**un `archive_sha256`**: distintas versiones no deben sumarse. No reemplazan las
vistas actuales de Power BI ni el registro de forecasting existente.

Un ejemplo de extracción tabular está en `powerbi/atlas_products.sql`.
El mismo pack sirve como fuente offline para una futura pantalla Android, web o
desktop. La vista HTML permite revisar el resultado antes de escribir ese cliente.

## Qué se implementó en cada uno de los 12 puntos

| Punto | Implementación verificable |
|---|---|
| 1. Responsabilidades | Módulo `publishing` aditivo; replica, analytics y consumidores independientes. |
| 2. Capa publish | Registro PostgreSQL inmutable y diez vistas de productos/evidencia. |
| 3. Data Product | Grano, dimensiones, métricas, calidad, procedencia y snapshot reconciliado. |
| 4. Model Product | Model Pack con MAE temporal, población, baseline, parámetros, resultado y limitaciones. |
| 5. Finding | Comparación trimestral calculada, referencias a indicadores, hipótesis y conclusiones prohibidas. |
| 6. DecisionInsight | Opciones, objetivo, restricciones, responsable pendiente, revisión y outcome no observado. |
| 7. Evidencia | Tipo y estatus explícitos; sin escalera engañosa de certeza L0–L6. |
| 8. Wisdom Card | Enseñanza enlazada a hallazgo, advertencia, aplicación y estatus educativo. |
| 9. Android/Packs | ZIP JSON acotado, manifest, importador Python de referencia y reemplazo atómico. |
| 10. Packs separados | Cuatro documentos versionados; referencias comprobadas antes de instalar. |
| 11. Model Factory | Pipeline snapshot → validación → baseline → evaluación → resultados → publicación. |
| 12. Historia completa | Stock/ventas/ritmo → modelo → hallazgo → escenario → decisión → historia interactiva. |

El baseline media móvil es deliberadamente sencillo. Los modelos ML existentes
siguen en `commercial_forecasting` y `model_control`: esta entrega no los vuelve
a entrenar, no promueve candidatos ni presenta este baseline como ML avanzado.
La primera familia exportable es `moving_average_3`. Un adaptador de resultados
de forecasting deberá preservar sus horizontes, intervalos, selección y evidencia
prospectiva antes de añadir otra familia al contrato.

## Validación y reproducibilidad

```powershell
python -m pip install -e ".[publishing,dev]"
python -m pytest tests/publishing tests/test_economics.py tests/test_decision_contracts.py
```

Mismos snapshot, timestamp, commit y bytes de builder producen el mismo ZIP.
Los timestamps ZIP son fijos y el JSON es canónico. SHA-256 detecta corrupción,
**no autentica al emisor**. Distribuir únicamente packs de origen confiable.
La versión del contrato desconocida se rechaza; no hay migración silenciosa.
El importador valida todo en memoria antes de sustituir el pack anterior.

La instalación de PostgreSQL y el refresco real necesitan ejecutarse en el PC del
usuario. Publicar el código en GitHub no instala nada en ese PC ni publica un APK.
No se reactivan GitHub Actions ni se crean tareas programadas.

## Cerrar el ciclo decisión → resultado

`publish.decision_event` conserva acciones y resultados posteriores sin modificar
el pack emitido. Crear un JSON local con el schema `decision-event.schema.json`:
`schema_version`, `archive_sha256`, `decision_id`, `event_type`
(`ACTION_RECORDED` u `OUTCOME_OBSERVED`), `occurred_at`, `note`, `value`, `unit`.
Un outcome exige valor numérico y unidad; una acción puede usar null en ambos.
Evitar nombres de personas o información de clientes en la nota.

```powershell
python scripts/publish_atlas.py record-decision --event artifacts/atlas/decision-event.json
```

La referencia a la decisión y release debe existir. Eventos idénticos se deduplican;
correcciones se agregan como nuevos eventos, no se borran resultados anteriores.
`publish.decision_learning` permite revisar esa experiencia. Un resultado posterior
no demuestra que la acción lo causó, ni promueve automáticamente una Wisdom Card
a regla empresarial. Este feedback permanece privado y no se añade al ZIP público.
