@echo off
cd /d "%~dp0..\backend"
if not exist .venv\Scripts\uvicorn.exe (echo Сначала запустите: python install.py & exit /b 1)
.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
