@echo off
cd /d "%~dp0..\frontend"
if not exist node_modules (echo Сначала запустите: python install.py & exit /b 1)
npm run dev
