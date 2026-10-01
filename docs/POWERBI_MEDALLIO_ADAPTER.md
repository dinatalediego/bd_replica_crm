# Adaptador Power BI -> Medallio

## Objetivo

Convertir el trabajo incremental hecho en Power BI en una fuente de requisitos ejecutables para Medallio.

Flujo:

~~~
C:\clientes\Cygnus\dashboards
        |
PBIP/TMDL/PBIR o PBIX
        |
extracción + normalización
        |
snapshot semántico versionado por hash
        |
diff contra la versión anterior
        |
clasificación: M / DAX / modelo / visual
        |
plan de traducción
        |
pruebas de paridad
        |
promoción a SQL/Python de Medallio
~~~

No se hace un reemplazo textual DAX -> Python. DAX puede depender del contexto de filtros y relaciones. El adaptador separa lo que conviene mover al backend de lo que debe seguir en la capa semántica o visual.

## Qué lee

1. PBIP + TMDL + PBIR: formato preferido porque el modelo y el reporte son texto y permiten un diff preciso.
2. PBIX/PBIT: compatible mediante pbi-tools extract.
3. PBIX sin pbi-tools: se registra la versión/hash, pero no se recupera la lógica DAX/M.

El estado local se guarda en .state/powerbi_adapter/ y no se versiona.

## Primera familia de reglas del dashboard de Calidad de Data

El dashboard actual muestra familias que son candidatas a convertirse en contratos de negocio de Medallio:

- conversión de separación: Inicial Cantada vs sin inicial (tubería);
- contratos: cargados contratos (OK), con pdf en blanco (eliminar), sin contratos cargados;
- proceso: flujos oficiales vs anteriores, adjuntos válidos vs en blanco;
- responsabilidad operativa: proceso cerrado, falta asesor, falta administración;
- calidad de datos: DNI, nombres, celular, email;
- universos: stock y propietarios.

El PDF sirve para validar resultados y vocabulario. Las fórmulas exactas deben venir de DAX/M/TMDL; no se reconstruyen desde una captura.

## Instalación local

Desde C:\Cygnus\projects\bd_replica_crm:

~~~powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e .
~~~

Para PBIX, instala pbi-tools y comprueba:

~~~powershell
pbi-tools info
~~~

La alternativa preferida es abrir el PBIX y usar Archivo > Guardar como > Power BI Project (.pbip). Para máxima trazabilidad, usar TMDL para el modelo y PBIR para el reporte.

## Configuración

config/powerbi_adapter.yml ya apunta a:

~~~
C:\clientes\Cygnus\dashboards
~~~

## Uso cotidiano

Deja o sobrescribe allí la versión más reciente y ejecuta:

~~~powershell
.\scripts\80_powerbi_adapter_scan.bat
~~~

Para una versión concreta:

~~~powershell
.\scripts\80_powerbi_adapter_scan.bat --input "C:\clientes\Cygnus\dashboards\Calidad de Data de Ventas y de Procesos.pbix"
~~~

Si guardaste como PBIP:

~~~powershell
.\scripts\80_powerbi_adapter_scan.bat --input "C:\clientes\Cygnus\dashboards\Calidad de Data de Ventas y de Procesos.pbip"
~~~

## Salidas

Cada corrida crea:

~~~
.state/powerbi_adapter/
+-- manifest.json
+-- extracted/
+-- snapshots/
|   +-- <snapshot_id>.json
+-- reports/
    +-- <snapshot_id>_progress.md
    +-- <snapshot_id>_translation_plan.json
~~~

progress.md responde "qué avancé desde la última versión". El JSON es el contrato para preparar cambios en sql/, src/replica_cygnus/ y tests/.

## Criterio de traducción

| Origen | Acción por defecto |
|---|---|
| Power Query M | promover a SQL/Python; alta prioridad |
| Columna/tabla calculada DAX | evaluar promoción a analytics |
| Medida DAX sin señales fuertes de contexto visual | candidata a métrica canónica |
| Medida con CALCULATE, ALLSELECTED, SELECTEDVALUE, ISINSCOPE, etc. | mantener semántica DAX o implementación dual |
| Relaciones/modelo | revisar contrato dimensional/mart |
| Páginas/visuales PBIR | no migrar al backend |

## Promoción a Medallio

La primera versión no escribe automáticamente reglas nuevas sobre producción. Esa separación es intencional:

1. detectar exactamente la diferencia;
2. generar candidato de traducción;
3. implementar SQL/Python en una rama;
4. comparar Power BI vs Medallio con los mismos filtros;
5. agregar prueba de regresión;
6. incorporar el cálculo al refresh maestro o a una vista/mart existente.

Cuando una regla ya está canonizada en Medallio, Power BI debe consumirla y dejar de recalcularla en M/DAX siempre que no dependa del contexto visual.

## Siguiente automatización

Después de validar 2 o 3 versiones reales, el adaptador puede evolucionar a una tarea diaria que revise hashes nuevos o a un watcher de guardado.

No se recomienda extraer PBIX dentro de cada refresh horario: el dashboard es una fuente de cambios de ingeniería, no una dependencia operativa de producción.
