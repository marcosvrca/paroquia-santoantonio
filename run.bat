@echo off
chcp 65001 >nul
if "%~1"=="__wait__" goto wait_and_open

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Executando instalacao...
  call "%~dp0setup.bat"
  if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERRO] Nao foi possivel ativar o ambiente virtual.
  echo Execute setup.bat e tente novamente.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao disponivel no ambiente virtual.
  pause
  exit /b 1
)

if not exist "data" mkdir data
if not exist "data\uploads" mkdir data\uploads
if not exist "data\nfe" mkdir data\nfe

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo Iniciando Festejo Financeiro em http://127.0.0.1:8000
start "" cmd /c ""%~f0" __wait__"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo [ERRO] O servidor nao iniciou. Verifique a mensagem acima.
  echo Se for a primeira vez neste PC, execute setup.bat
  pause
)
exit /b

:wait_and_open
:waitloop
netstat -ano | findstr :8000 | findstr LISTENING >nul
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitloop
)
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
  start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "http://127.0.0.1:8000"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
  start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" "http://127.0.0.1:8000"
) else (
  start "" "http://127.0.0.1:8000"
)
exit /b
