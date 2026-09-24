@echo off
REM ============================================================
REM  賽馬 AI 自動分析系統 - Windows 啟動腳本
REM  雙擊運行，或在 CMD / PowerShell 執行： start_server.bat
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title 賽馬 AI 自動分析系統 - 後端伺服器
echo.
echo    \    / |  | _ _  _  ._  _.
echo     \/\/  |/\| (- (_)| | (_|
echo.
echo ==========================================================
echo   🐎 香港賽馬 AI 自動分析系統
echo ==========================================================
echo.
echo   [*] 正在啟動後端伺服器 (port 8080) ...
echo   [*] 數據每 5 分鐘自動刷新
echo   [*] 瀏覽器將會自動開啟 http://localhost:8080
echo.

where python.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=python.exe"
    goto :run
)
where py.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py.exe"
    goto :run
)
where python3.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=python3.exe"
    goto :run
)
echo [ERROR] 找不到 Python，請先安裝 Python 3.7+
pause
exit /b 1

:run
start "" "http://localhost:8080"
%PY% app.py
pause
