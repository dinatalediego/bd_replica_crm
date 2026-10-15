# Laboratorio económico de audiencias — agencia digital

## Objetivo

`notebooks/13_marketing_agency_audiences_economics_lab.ipynb` es el laboratorio especializado en los medios gestionados por la agencia tercerizada de marketing digital. Reutiliza el enfoque del notebook 12, separa el universo de agencia del resto de medios y genera un Excel ejecutivo/operativo.

La selección de medios vive en `config/marketing_agency_channels.yml`. La configuración inicial corresponde al filtro entregado el 2026-10-15:

- Facebook
- Tik Tok (`tik tok` y alias `tiktok`)
- Instagram
- Meta
- Google

Las métricas del CSV de referencia no se fijan en código: el notebook siempre recalcula los resultados contra `analytics.marketing_audiencias`.

## Qué analiza

1. Escala, tasa positiva, remarketing y aptitud externa por medio.
2. Concentración de captación mediante HHI.
3. Intervalos Wilson al 95% para las tasas.
4. Prueba chi-cuadrado global y comparaciones de proporciones con ajuste de Holm.
5. Matriz proyecto × canal.
6. Cohortes mensuales para evitar comparar bases con distinta maduración.
7. Stock de RMKT activable.
8. Separación explícita entre asociación histórica y causalidad.

## Excel generado

Cada ejecución crea:

`outputs/marketing_agency_audiences/audiencias_agencia_ejecutivo_YYYYMMDD_HHMMSS.xlsx`

Hojas:

- `00_Resumen`: KPIs ejecutivos.
- `01_Canales`: volumen, tasas, intervalos, participación y stock.
- `02_Proyecto_Canal`: detalle agregado para filtros.
- `03_Cohortes`: desempeño mensual por medio.
- `04_Hipotesis`: comparaciones contra el canal benchmark.
- `10_Base_Positiva`: base positiva apta para entrega externa.
- `11_Base_Negativa`: base RMKT negativa apta para entrega externa.

Las dos hojas operativas pueden contener nombres, teléfonos y correos. Se construyen desde las vistas de marketing y exigen `apto_entrega_externa = TRUE`; esas filas no se muestran en pantalla dentro del notebook.

## Instalación / ejecución en VS Code

Desde la raíz de `bd_replica_crm`, en PowerShell:

```powershell
git fetch origin
git switch feat/medallio-refresh-hardening-review
git pull

$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -e .
& $python -m pip install ipykernel matplotlib scipy
& $python -m ipykernel install --user --name medallio-dw --display-name "Python (Medallio DW)"

code .\notebooks\13_marketing_agency_audiences_economics_lab.ipynb
```

Seleccionar el kernel **Python (Medallio DW)** y ejecutar `Run All`.

## Cambiar los medios de la agencia

Editar únicamente `config/marketing_agency_channels.yml`.

Cada canal tiene:

- `key`: identificador estable;
- `label`: nombre visible;
- `match_values`: valores aceptados en `medio_captacion`.

No es necesario modificar SQL o gráficos para incorporar un alias nuevo.

## Regla de privacidad

El bloque analítico no consulta PII. Las bases de activación se consultan recién en la sección de exportación y solo para filas aptas para entrega externa. Si el objetivo es análisis y no activación, se puede detener la ejecución antes de esa sección.
