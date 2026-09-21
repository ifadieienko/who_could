@echo off
call "%~dp0scripts\start-database.cmd"
start "Who could backend" cmd /k "%~dp0scripts\start-backend.cmd"
start "Who could frontend" cmd /k "%~dp0scripts\start-frontend.cmd"
