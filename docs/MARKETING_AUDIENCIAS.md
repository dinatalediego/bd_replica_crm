# Audiencias de Marketing - LAL y RMKT

## Resultado

El refresh canónico de Medallio mantiene un mart local de personas para análisis y preparación de audiencias. La construcción ocurre después de `staging.clientes_calidad` y usa únicamente PostgreSQL local; no añade consultas a Redshift.

| Producto | Regla | Uso sugerido |
|---|---|---|
| `analytics.v_marketing_positiva` | Alguna proforma, separación o minuta/venta | Semilla LAL o segmentación de alta intención |
| `analytics.v_marketing_negativa_sin_avance` | Sin esos avances y cliente creado hace 180 días o más | Análisis de no conversión; su activación requiere criterio de campaña |
| `analytics.v_marketing_exclusiones` | Minuta/venta, contacto inválido o supresión explícita | Exclusión de campañas de captación |
| `analytics.v_marketing_audiencias_health` | Conteos y última actualización, sin PII | Control operativo en Power BI |

Las bases incluyen los cuatro campos solicitados: `Nombres`, `Apellidos`, `Telefono_Celular` y `Correo_electronico`. No se filtra el medio de captación: puede ser orgánico, feria, portal u otro origen registrado.

Una persona convertida puede aparecer como positiva (buena semilla LAL) y como exclusión (no volver a mostrarle una campaña de captación). Los grupos no deben sumarse como si fueran mutuamente excluyentes.

## Privacidad y entrega

El sistema no presume consentimiento. `analytics.marketing_consentimientos` comienza vacío y debe recibir evidencia autorizada. `analytics.marketing_supresiones` conserva solicitudes de no contacto u otras exclusiones documentadas. `apto_entrega_externa` solo es verdadero cuando el contacto es válido, existe consentimiento vigente y no hay supresión activa.

No exportar al proveedor filas con `apto_entrega_externa = false`. El documento de identidad se utiliza internamente para enlazar y deduplicar, pero no se expone en las vistas de entrega.

## Instalación inicial desde VS Code (PowerShell)

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
& $python .\scripts\check_marketing_audiences.py
```

Consulta de control:

```sql
SELECT * FROM analytics.v_marketing_audiencias_health;
SELECT etapa_maxima, count(*)
FROM analytics.marketing_audiencias
GROUP BY etapa_maxima
ORDER BY etapa_maxima;
```

## Permanencia en la tarea programada

`scripts/run_hourly.bat` continúa siendo el único punto de entrada de Windows y ejecuta `scripts/dw_refresh.py --mode hourly`. El orquestador ahora incluye `02c_marketing_audiences_refresh` inmediatamente después de `02b_clientes_calidad_refresh`. Por ello no se crea una segunda tarea y no aumenta la frecuencia de Redshift.

Verificación en PowerShell:

```powershell
schtasks /Query /TN "Medallio - Replica Redshift Local" /V /FO LIST
Get-Content .\logs\dw_refresh.log -Tail 120 | Select-String "marketing_audiences|DW_REFRESH"
```

Para una prueba sin tocar Redshift:

```powershell
& $python .\scripts\dw_refresh.py --local-only --mode manual
```

El resultado esperado contiene `OK 02c_marketing_audiences_refresh`, `Gate marketing_audiencias APROBADO` y `DW_REFRESH_OK`.

## Power BI

1. En Power BI Desktop, elegir **Obtener datos > PostgreSQL**.
2. Indicar el servidor PostgreSQL local y la base `medallio_dw`; usar modo **Importar**.
3. Seleccionar las tres vistas de audiencias y `v_marketing_audiencias_health` dentro de `analytics`.
4. Como alternativa, crear consultas en blanco y copiar los archivos `powerbi/M/qMarketing*.m`.
5. Usar la vista `health` en una página de control y mostrar última actualización, positivas, negativas, exclusiones y aptas para entrega.
6. En Power BI Service, la actualización de PostgreSQL local requiere la puerta de enlace instalada y activa en la PC.

## Parámetros y operación

La ventana de no avance predeterminada es 180 días. Puede cambiarse solo de forma explícita:

```powershell
& $python .\scripts\refresh_marketing_audiences.py --inactivity-days 120
```

Para cambiar de forma permanente la tarea, definir `MARKETING_INACTIVITY_DAYS` en el entorno que ejecuta Windows Task Scheduler. Registrar el cambio como decisión de negocio.
