@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "data\festejo.db" (
  echo [ERRO] Banco local nao encontrado em data\festejo.db
  pause
  exit /b 1
)

if not exist "bootstrap_data" mkdir bootstrap_data
if not exist "bootstrap_data\uploads" mkdir bootstrap_data\uploads
if not exist "bootstrap_data\nfe" mkdir bootstrap_data\nfe

copy /Y "data\festejo.db" "bootstrap_data\festejo.db" >nul
xcopy /Y /E /I "data\uploads\*" "bootstrap_data\uploads\" >nul
xcopy /Y /E /I "data\nfe\*" "bootstrap_data\nfe\" >nul

echo Bootstrap atualizado com os dados locais.
echo Rode git add bootstrap_data e commit antes do deploy.
pause
