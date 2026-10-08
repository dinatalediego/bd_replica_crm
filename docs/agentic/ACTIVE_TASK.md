# Active Task

Task ID: MEDALLIO-OS-MVP-001
Title: Construir Medallio OS local sobre kernels, notebooks y Ambassador
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/medallio-os-mvp
Base branch: main

## Result

Se implementó un MVP Streamlit local con Home, Control Tower, Executive Briefing,
Forecast Studio, Econometrics Lab, Project Benchmark Lab, Data Quality Center y
Notebook Launcher. La ejecución de notebooks usa copias en `.medallio/runs/` y
valida que notebook y kernel pertenezcan al runtime local permitido.

El runner `scripts/medallio_ambassador/run_ambassador.py` no está en `main` al
momento de este trabajo, pero la UI lo descubre dinámicamente si existe en el
working tree local (como en la captura del usuario).

Validación aislada sobre el mismo código fuente: 12 pruebas enfocadas aprobadas y
compilación Python sin errores. No se ejecutó el CI completo del repositorio ni se
fusionó a `main`.

## Next action

Revisar el PR de `feat/medallio-os-mvp`. En el PC local, preservar cambios sin
commit, traer la rama sin descartarlos, instalar `apps/medallio_os/requirements.txt`
y ejecutar `scripts/run_medallio_os.ps1` o `python -m streamlit run
apps/medallio_os/app.py`.
