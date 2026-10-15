# Medallio OS — MVP local

Capa Streamlit para operar los activos analíticos que ya existen en `bd_replica_crm`:
kernels Jupyter, notebooks, Medallio Ambassador y archivos de análisis.

## Qué funciona en este MVP

- **Home**: inventario automático de kernels/notebooks.
- **Control Tower**: preflight del runtime y ejecuciones recientes.
- **Executive Briefing**: invoca `scripts/medallio_ambassador/run_ambassador.py`
  cuando está presente en el working tree.
- **Forecast Studio**: descubre notebooks de forecasting/ML y los ejecuta con el
  kernel elegido.
- **Econometrics Lab**: descubre notebooks causal/econométricos y permite usar
  `cygnus-estadistica` u otro kernel.
- **Project Benchmark Lab**: carga CSV/XLSX, normaliza por proyecto a Mes 0 y
  compara su evolución.
- **Data Quality Center**: perfil de nulos, duplicados, cardinalidad y tipos.
- **Notebook Launcher**: catálogo y ejecución general.

Los notebooks se ejecutan sobre una **copia** en `.medallio/runs/<timestamp>/`.
El fuente nunca se sobrescribe.

## Instalar

Desde la raíz del repositorio y con `.venv` activo:

```powershell
python -m pip install -e .
python -m pip install -r apps\medallio_os\requirements.txt
```

## Ejecutar

```powershell
python -m streamlit run apps\medallio_os\app.py
```

o:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_medallio_os.ps1
```

Streamlit abrirá normalmente `http://localhost:8501`.

## Relación con tu working tree local

El MVP **no duplica** `run_ambassador.py`. Lo descubre en tiempo de ejecución.
Por eso, si ese runner y los notebooks `Medallio_CEO_5_Minute_AI_Briefing.ipynb`
y `Medallio_Enterprise_AI_Control_Tower_v2.ipynb` todavía existen solo en tu
computadora, la app los verá al ejecutarse desde esa misma copia.

## Seguridad operativa

- No usa `shell=True`.
- No recibe comandos libres desde la UI.
- Solo ejecuta notebooks ubicados dentro del repositorio.
- Solo admite kernels detectados por `jupyter kernelspec list --json`.
- No requiere subir datos a internet: CSV/XLSX se procesan dentro del proceso local.
- La ejecución real de Ambassador requiere habilitación explícita en la UI.
