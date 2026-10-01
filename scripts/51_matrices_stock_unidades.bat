@echo off
setlocal
cd /d "%~dp0.."

echo ================================================
echo MEDALLIO - MATRICES STOCK Y UNIDADES
echo ================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo [1/3] Verificando Streamlit...
%PYTHON% -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Streamlit no esta instalado. Instalando dependencias...
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo [2/3] Validando Medallio y capa de stock...
%PYTHON% scripts\stock_export.py --install-only
if errorlevel 1 goto :error

echo [3/3] Abriendo interfaz local...
echo.
echo URL esperada: http://localhost:8501
echo Para cerrar la interfaz presiona CTRL+C en esta ventana.
echo.
%PYTHON% -m streamlit run scripts\stock_matrix_app.py --server.address localhost --server.port 8501
if errorlevel 1 goto :error

endlocal
exit /b 0

:error
echo.
echo ERROR: no se pudo iniciar la interfaz.
echo Revisa .env, PostgreSQL medallio_dw y requirements.txt.
pause
endlocal
exit /b 1
