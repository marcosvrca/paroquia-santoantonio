@echo off
if "%~1"=="__wait__" goto wait_and_open

cd /d "%~dp0"
call .venv\Scripts\activate.bat
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Iniciando Festejo Financeiro em http://127.0.0.1:8000
start "" cmd /c ""%~f0" __wait__"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
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
  start chrome "http://127.0.0.1:8000"
)
exit /b
