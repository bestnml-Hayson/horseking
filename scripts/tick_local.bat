@echo off
rem One race-day tick, fired by Windows Task Scheduler every 15 minutes.
rem pythonw.exe keeps it windowless; output goes to logs\tick_local.log.
setlocal
set "PY=C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0tick_local.py"
