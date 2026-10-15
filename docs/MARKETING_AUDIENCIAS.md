# Audiencias de Marketing - LAL y RMKT

## Resultado

El refresh canónico de Medallio mantiene un mart local de personas para análisis y preparación de audiencias. La construcción ocurre después de `staging.clientes_calidad` y usa únicamente PostgreSQL local; no añade consultas a Redshift.

| Producto | Regla | Uso sugerido |
|---|---|---|
| `analytics.v_marketing_positiva` | Alguna proforma, separación o minuta/venta | Semilla LAL o segmentación de alta intención |
| `analytics.v_marketing_negativa_sin_avance` | Sin esos avances y cliente creado hace 180 días o más | Análisis de no conversión / RMKT interno |
| `analytics.v_marketing_neutral_reciente` | Sin avance, pero todavía fuera de la ventana RMKT | Seguimiento reciente |
| `analytics.marketing_audiencias_proyectos` | Persona × proyecto | Linaje de captación, proforma y conversión |
| `analytics.v_marketing_exclusiones` | Minuta/venta, contacto inválido o supresión explícita | Exclusión de campañas de captación |
| `analytics.v_marketing_audiencias_health` | Conteos, cobertura de proyecto y última actualización | Control operativo |

Las vistas operativas incluyen `Nombres`, `Apellidos`, `Telefono_Celular` y `Correo_electronico`. El documento de identidad se usa solo internamente para enlazar y deduplicar.

Una persona convertida puede aparecer como positiva y como exclusión; los grupos no deben sumarse como si fueran mutuamente excluyentes.

## Linaje de proyecto

El campo de proyecto ya no depende únicamente de `raw_cygnus.clientes`.

Fuentes:

1. `raw_cygnus.clientes_proyectos` → proyecto/medio de origen;
2. `raw_cygnus.proformas` → proyecto de proforma;
3. `raw_cygnus.procesos` → proyecto de separación/minuta/venta;
4. `raw_cygnus.proyectos` → nombre canónico;
5. `staging.clientes_calidad` → fallback.

Campos principales:

- `codigo_proyecto_origen`
- `proyecto_origen`
- `codigo_proyecto_proforma`
- `proyecto_proforma`
- `codigo_proyecto_conversion`
- `proyecto_conversion`
- `proyecto`
- `fuente_proyecto`
- `cambio_proyecto`
- `fecha_origen_primario`

Regla de resolución:

`ORIGEN > CONVERSION > PROFORMA > CLIENTE`

El detalle multi-proyecto vive en `analytics.marketing_audiencias_proyectos`, cuya llave es:

`persona_key + codigo_proyecto`

De esta forma una persona puede haber llegado por Matera, proformado Matera y finalmente convertido en Torre Nápoles sin perder ninguna de las tres evidencias.

## Medio y fecha de captación

Cuando existe evidencia en `clientes_proyectos`:

- `medio_captacion_origen` conserva el medio del primer touch del proyecto origen;
- `medio_captacion_cliente` conserva el valor de `clientes_calidad`;
- `medio_captacion` usa el origen y hace fallback al cliente.

`fecha_cliente` usa `fecha_origen_primario` y hace fallback a la fecha del cliente CRM. `fecha_cliente_crm` conserva la fecha anterior para auditoría.

## Privacidad y entrega

El sistema no presume consentimiento.

`analytics.marketing_consentimientos` comienza vacío y debe recibir evidencia autorizada.

`analytics.marketing_supresiones` conserva solicitudes de no contacto u otras exclusiones documentadas.

`apto_entrega_externa` solo es verdadero cuando:

- el contacto es válido;
- existe consentimiento vigente;
- no existe supresión activa.

Las vistas positiva, negativa y neutral sirven para trabajo interno con contactos válidos y no suprimidos. Para entregar una base a un tercero se debe filtrar además `apto_entrega_externa = TRUE`.

No forzar este flag manualmente.

## Instalación / upgrade desde VS Code

Ejecutar desde la raíz local del repositorio y con la tarea horaria detenida:

```powershell
git status -sb
git fetch origin
git switch feat/medallio-refresh-hardening-review
git pull --ff-only origin feat/medallio-refresh-hardening-review

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "..\.venv\Scripts\python.exe" }

& $python -m pip install -e .

& $python .\scripts\schema_sync.py --only marketing_audiences
& $python .\scripts\refresh_marketing_audiences.py

& $python -m pytest `
    tests\test_marketing_audiences.py `
    tests\test_marketing_agency_audiences_notebook.py `
    -q
```

Consulta de control:

```sql
SELECT *
FROM analytics.v_marketing_audiencias_health;
```

Cobertura del linaje:

```sql
SELECT
    fuente_proyecto,
    count(*) AS personas
FROM analytics.marketing_audiencias
GROUP BY fuente_proyecto
ORDER BY personas DESC;
```

Muestra de cambios de proyecto:

```sql
SELECT
    proyecto_origen,
    proyecto_proforma,
    proyecto_conversion,
    count(*) AS personas
FROM analytics.marketing_audiencias
WHERE cambio_proyecto
GROUP BY
    proyecto_origen,
    proyecto_proforma,
    proyecto_conversion
ORDER BY personas DESC;
```

## Permanencia en la tarea programada

`scripts/run_hourly.bat` continúa siendo el único punto de entrada de Windows y ejecuta `scripts/dw_refresh.py --mode hourly`.

El orquestador mantiene `02c_marketing_audiences_refresh` inmediatamente después de `02b_clientes_calidad_refresh`.

El refresh usa las tablas RAW locales ya sincronizadas, por lo que no se crea una segunda tarea ni se añade una consulta independiente a Redshift.

Verificación:

```powershell
schtasks /Query /TN "Medallio - Replica Redshift Local" /V /FO LIST

Get-Content .\logs\dw_refresh.log -Tail 120 |
    Select-String "marketing_audiences|DW_REFRESH"
```

Prueba sin tocar Redshift:

```powershell
& $python .\scripts\dw_refresh.py --local-only --mode manual
```

## Notebook de agencia y ventana temporal

`notebooks/13_marketing_agency_audiences_economics_lab.ipynb` admite:

```python
FECHA_INICIO = "01/07/26"
FECHA_CORTE = "15/10/26"
```

o límites abiertos:

```python
FECHA_INICIO = None
FECHA_CORTE = None
```

La ventana se interpreta por fecha de origen del lead, no por fecha de exportación del Excel.

El mismo periodo se aplica a:

- estadística descriptiva;
- canales;
- cohortes;
- hipótesis;
- proyecto origen;
- flujos origen → proforma → conversión;
- bases positivas;
- RMKT;
- neutrales;
- exportables.

## Power BI

1. En Power BI Desktop, elegir **Obtener datos > PostgreSQL**.
2. Indicar PostgreSQL local y la base `medallio_dw`; usar modo **Importar**.
3. Seleccionar las vistas de audiencias, `marketing_audiencias_proyectos` y `v_marketing_audiencias_health`.
4. Usar `proyecto_origen` para análisis de captación.
5. Usar `proyecto_conversion` para análisis de cierre.
6. Usar `cambio_proyecto` para sustitución/cross-selling.
7. En Power BI Service, PostgreSQL local requiere la puerta de enlace activa.

## Parámetros y operación

La ventana de no avance predeterminada continúa siendo 180 días:

```powershell
& $python .\scripts\refresh_marketing_audiencias.py --inactivity-days 120
```

Este parámetro define qué se considera RMKT.

Es distinto de `FECHA_INICIO` / `FECHA_CORTE` del notebook: esos parámetros solo recortan el universo que se quiere analizar/exportar.
