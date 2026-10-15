# MEDALLIO: fuente mínima de modelado en Supabase

## Propósito y límites

Este piloto usa el Supabase ya conectado al repositorio, donde existen esquemas privados `medallio_*` sin cargas de MEDALLIO. Añade `medallio_pilot`, independiente de la réplica completa prevista en `scripts/sync_medallio_to_supabase.py`. Ese script copia tablas físicas y puede incluir datos personales; no debe ejecutarse para este piloto.

El sistema local `medallio_dw` sigue siendo la fuente de verdad. El mart remoto contiene únicamente una fila agregada por proyecto y mes de `analytics.comercial_proyecto_mes`. No contiene nombres de proyecto, cliente, unidad, proforma, asesor, texto libre ni precios individuales. La referencia del proyecto se deriva mediante HMAC-SHA256 con una clave que permanece en el PC. Los conteos agregados también son información comercial sensible: un responsable de datos debe aprobar el paquete concreto antes de su exportación.

| Objeto | Grano | Uso |
|---|---|---|
| `medallio_pilot.project_month` | proyecto pseudónimo × mes | stock inicial/final, ventas, días de exposición, calidad, corte, mes parcial y procedencia |
| `medallio_pilot.v_next_month_training` | par de meses consecutivos completos | predictores conocidos al cierre de un mes y ventas del siguiente; excluye unidades pendientes de revisión |

La vista es **histórica retrospectiva revisada**, no prueba de pronóstico emitido prospectivamente ni de causalidad. Un primer baseline puede comparar promedio móvil/estacional frente a la realidad futura, separando proyectos y meses para evitar fuga temporal. La tabla no reemplaza el registro de forecasts existente.

Ejemplo de baseline ingenuo que usa las ventas del mes cerrado como predicción del siguiente:

```sql
SELECT data_origin, count(*) AS pares,
       avg(abs(target_sales_units - sales_previous_month)) AS mae_unidades
FROM medallio_pilot.v_next_month_training
GROUP BY data_origin;
```

La prueba remota inicial insertó **24 filas sintéticas** de dos proyectos ficticios (enero a diciembre de 2025), produjo **22 pares consecutivos**, cero errores de conciliación y MAE sintético de **1,364 unidades**. Esta cifra solo demuestra que el contrato y la consulta funcionan; no mide desempeño comercial real.

## Seguridad

El esquema no se configura en Data API. Revoca `USAGE` de `anon`, `authenticated` y `service_role`; la tabla tiene RLS activo sin políticas públicas. La vista utiliza `security_invoker=true`. Se accede por PostgreSQL desde un proceso autorizado, no mediante una clave publicable ni desde el navegador. Revisar que el proyecto Supabase mantenga `medallio_pilot` fuera de los esquemas expuestos. Supabase distingue entre privilegios `GRANT` y políticas RLS; ambos importan. [Documentación de seguridad de API](https://supabase.com/docs/guides/api/securing-your-api).

El operador necesita un secreto `MEDALLIO_EXPORT_HMAC_KEY` de al menos 32 bytes aleatorios, estable entre ejecuciones y nunca incluido en Git. La rotación cambiaría las referencias de proyecto y exige un procedimiento de migración. `MEDALLIO_DSN` da acceso de lectura al PostgreSQL local; `SUPABASE_DB_URL` debe ser una conexión TLS autorizada al proyecto seleccionado. La preparación no abre conexiones de red cuando usa un fixture sintético.

## Operación manual

El esquema está versionado en `sql/116_supabase_minimal_mart/01_private_project_month.sql`. Se aplica como migración `medallio_minimal_project_month_v1` al proyecto Supabase identificado tras revisión de los permisos. No se integra en `schema_sync.py` de la réplica horaria.

En el PC, desde la raíz del repositorio, después de configurar los tres secretos en el entorno y revisar el corte:

```powershell
$env:PYTHONPATH="src"
python scripts/sync_minimal_supabase_mart.py prepare --project MD --from-month 2024-01-01 --output .\private\md_project_month.json
```

Inspeccionar la lista exacta de agregados y su origen. El archivo preparado no contiene el código del proyecto, pero sigue siendo comercialmente sensible; guardarlo fuera de Git con controles de acceso y borrarlo según la política de retención. Publicar únicamente cuando el responsable autorice ese archivo:

```powershell
python scripts/sync_minimal_supabase_mart.py publish --packet .\private\md_project_month.json --approved-export
```

La carga hace `UPSERT` solo del mismo origen, compara hashes de cada fila al terminar y revierte la transacción si no concilian. No borra, trunca ni toca la réplica local. Los meses históricos pueden cambiar por anulaciones conocidas después: `source_hash` cambia cuando cambian los agregados y `source_cutoff` registra el corte consultado. La tabla conserva solo la versión actual de cada mes. Para evaluación prospectiva se requieren snapshots inmutables adicionales.

Prueba sin credenciales:

```powershell
$env:PYTHONPATH="src"
python tests/test_supabase_mart.py
```

Antes de cargar datos empresariales, comprobar la autorización para alojarlos en el proyecto Supabase personal, la región, el acuerdo de tratamiento y el acceso a la base. El piloto remoto inicial usa solo registros sintéticos. Una conexión directa a la base requiere un rol con privilegios adecuados; no usar claves `anon` o `service_role` en Power BI ni en clientes públicos.
