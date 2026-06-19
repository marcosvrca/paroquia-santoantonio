@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Iniciando Festejo Financeiro em http://127.0.0.1:8000
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000