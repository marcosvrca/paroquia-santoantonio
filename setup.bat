@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Festejo Financeiro - Instalacao
echo ============================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
  goto check_py
)

where python >nul 2>&1
if %errorlevel%==0 (
  set "PY=python"
  goto check_py
)

echo [ERRO] Python nao encontrado.
echo.
echo Instale Python 3.10 ou superior em:
echo   https://www.python.org/downloads/
echo.
echo Marque a opcao "Add Python to PATH" durante a instalacao.
pause
exit /b 1

:check_py
echo Verificando Python...
%PY% --version
if errorlevel 1 (
  echo [ERRO] Nao foi possivel executar Python.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Criando ambiente virtual (.venv)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar .venv
    pause
    exit /b 1
  )
)

echo.
echo Instalando dependencias...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias.
  pause
  exit /b 1
)

if not exist "data" mkdir data
if not exist "data\uploads" mkdir data\uploads
if not exist "data\nfe" mkdir data\nfe

echo.
echo ============================================
echo   Instalacao concluida!
echo   Execute run.bat para iniciar o sistema.
echo ============================================
echo.
pause
