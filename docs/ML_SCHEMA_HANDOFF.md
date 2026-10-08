# Primer paquete local para preparar ML con Medallio

El código del repositorio ya documenta el caso de priorización de leads. La
captura de pgAdmin muestra los esquemas de `medallio_dw`, pero no confirma qué
tablas y columnas existen hoy en tu PC. Este paso captura esa estructura sin
exportar registros de clientes.

Desde la raíz de `bd_replica_crm`, con el entorno virtual ya instalado:

```powershell
.\.venv\Scripts\python.exe scripts\export_ml_schema_package.py
```

El comando lee solo catálogos de **PostgreSQL local** y deja un ZIP en
`artifacts/ml_schema_handoff/`. La carpeta está ignorada por Git. No utiliza
Redshift, no cambia tablas y no envía nada a internet.

Abre el ZIP para revisar `relations.csv`, `columns.csv`, `keys.csv`,
`manifest.json` y `README.txt`. Luego comparte aquí ese ZIP. Las cantidades
de filas son estimaciones del catálogo; una vista puede no tener estimación.
Las relaciones de negocio sin claves foráneas declaradas requerirán revisión
del código y de datos agregados en la siguiente etapa.

No subas `.env`, credenciales ni las salidas del script existente
`profile_interaction_contract.py`: su archivo `category_top_values.csv` puede
contener valores de columnas personales. Tras revisar este paquete de esquema
se puede construir una segunda exportación de perfiles agregados y, solo si
hace falta, una muestra anonimizada específica para leads.
