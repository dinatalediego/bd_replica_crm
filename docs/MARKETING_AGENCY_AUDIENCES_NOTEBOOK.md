# Laboratorio económico de audiencias — agencia digital

## Objetivo

`notebooks/13_marketing_agency_audiences_economics_lab.ipynb` es el laboratorio especializado en los medios gestionados por la agencia tercerizada de marketing digital.

El notebook usa el mart local `analytics.marketing_audiencias`, pero ahora el proyecto ya no depende solo de `staging.clientes_calidad`.

El refresh resuelve el linaje comercial con estas fuentes:

1. `raw_cygnus.clientes_proyectos` → proyecto y medio de **origen**;
2. `raw_cygnus.proformas` → proyecto de **proforma**;
3. `raw_cygnus.procesos` → proyecto de **separación/minuta/venta**;
4. `raw_cygnus.proyectos` → catálogo código → nombre;
5. `staging.clientes_calidad` → fallback de cliente y controles de contacto.

La prioridad del campo analítico `proyecto` es:

`ORIGEN > CONVERSION > PROFORMA > CLIENTE`

El linaje completo se conserva además en:

`analytics.marketing_audiencias_proyectos`

con granularidad `persona_key + codigo_proyecto`.

## Medios de agencia

La selección vive en `config/marketing_agency_channels.yml`.

Configuración inicial:

- Facebook
- Tik Tok (`tik tok` y `tiktok`)
- Instagram
- Meta
- Google

Las métricas nunca quedan hardcodeadas; se recalculan desde Medallio local.

## Ventana temporal opcional

En la primera celda de parámetros:

```python
FECHA_INICIO = "01/07/26"
FECHA_CORTE = "15/10/26"
```

También se admite:

```python
FECHA_INICIO = None
FECHA_CORTE = None
```

Formatos aceptados:

- `DD/MM/YY`
- `DD/MM/YYYY`
- `YYYY-MM-DD`

La fecha de análisis es `fecha_origen_primario`; si no existe, usa `fecha_cliente`.

El mismo filtro gobierna estadísticas, gráficos y bases Excel para evitar universos inconsistentes.

## Qué analiza

1. escala y tasa positiva por medio;
2. HHI de concentración;
3. intervalos Wilson 95%;
4. chi-cuadrado y comparaciones de proporciones con Holm;
5. proyecto origen × medio;
6. cohortes por fecha de captación;
7. proyecto origen → proforma → conversión;
8. cambios de proyecto y sustitución/cross-selling;
9. relaciones multi-proyecto;
10. stock positivo, RMKT y neutral reciente;
11. separación entre bases internas y exportables.

Las diferencias históricas son asociación, no causalidad. Para medir lift incremental se requiere grupo control o un diseño causal defendible.

## Campos de proyecto

`analytics.marketing_audiencias` expone:

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

`cambio_proyecto = TRUE` cuando el proyecto de origen difiere del proyecto de conversión; mientras aún no existe conversión, la proforma funciona como evidencia secundaria.

## Excel generado

Salida:

```text
outputs/marketing_agency_audiences/
audiencias_agencia_<inicio>_<corte>_YYYYMMDD_HHMMSS.xlsx
```

Hojas:

- `00_Resumen`
- `01_Canales`
- `02_Proyecto_Origen`
- `03_Cohortes`
- `04_Hipotesis`
- `05_Origen_Conversion`
- `06_Flujo_Proyectos`
- `07_Proyecto_Detalle`
- `10_Positiva_Interna`
- `11_Negativa_RMKT_Interna`
- `12_Neutral_Reciente`
- `20_Positiva_Exportable`
- `21_Negativa_Exportable`

Las hojas 10/11/12 son internas.

Las hojas 20/21 contienen únicamente filas con `apto_entrega_externa = TRUE`.

## Instalación / actualización

Desde la raíz de `bd_replica_crm`:

```powershell
git fetch origin
git switch feat/medallio-refresh-hardening-review
git pull --ff-only origin feat/medallio-refresh-hardening-review

$python = ".\.venv\Scripts\python.exe"

& $python -m pip install -e .

& $python .\scripts\schema_sync.py --only marketing_audiences
& $python .\scripts\refresh_marketing_audiences.py

& $python -m pytest `
    tests\test_marketing_audiences.py `
    tests\test_marketing_agency_audiences_notebook.py `
    -q

code .\notebooks\13_marketing_agency_audiences_economics_lab.ipynb
```

Después seleccionar el kernel **Python (Medallio DW)** y ejecutar **Restart Kernel → Run All**.

## Control rápido del nuevo linaje

```sql
SELECT
    personas,
    positivas,
    negativas_sin_avance,
    con_proyecto_origen,
    con_proyecto_conversion,
    cambios_proyecto,
    project_links
FROM analytics.v_marketing_audiencias_health;
```

Cobertura del proyecto origen:

```sql
SELECT
    fuente_proyecto,
    count(*) AS personas
FROM analytics.marketing_audiencias
GROUP BY fuente_proyecto
ORDER BY personas DESC;
```

Flujos entre proyectos:

```sql
SELECT
    proyecto_origen,
    proyecto_conversion,
    count(*) AS personas
FROM analytics.marketing_audiencias
WHERE proyecto_origen IS NOT NULL
  AND proyecto_conversion IS NOT NULL
GROUP BY proyecto_origen, proyecto_conversion
ORDER BY personas DESC;
```

## Privacidad

`analytics.marketing_consentimientos` sigue siendo la fuente explícita de autorización publicitaria.

No se modifica ni se fuerza `apto_entrega_externa`.

La ausencia de consentimiento no elimina las bases internas, pero sí mantiene vacías las hojas exportables hasta que exista evidencia válida.
