@echo off
cd /d "%~dp0..\backend"
set PYTHON=python
if exist .venv\Scripts\python.exe set PYTHON=.venv\Scripts\python.exe
if "%1"=="--reset" (%PYTHON% -m app.database --reset) else (%PYTHON% -m alembic upgrade head)
