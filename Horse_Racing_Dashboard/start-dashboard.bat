@echo off
REM ──────────────────────────────────────────────
REM Horse Racing Dashboard — Windows Start Script
REM Double-click to start the dashboard locally
REM ──────────────────────────────────────────────

set "DASHBOARD_DIR=%~dp0"
set "LOG_DIR=%DASHBOARD_DIR%logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo %date% %time% — Starting Horse Racing Dashboard... >> "%LOG_DIR%\startup.log"

REM Kill any existing processes on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F 2>nul

REM 1. Start Auto-Regenerate Watcher
start /B python "%DASHBOARD_DIR%auto_regenerate.py" >> "%LOG_DIR%\auto_regenerate.log" 2>&1
echo %date% %time% — Auto-regenerate watcher started >> "%LOG_DIR%\startup.log"

REM 2. Start Backend
cd /d "%DASHBOARD_DIR%backend"
start /B python -m uvicorn main:app --host 0.0.0.0 --port 8000 >> "%LOG_DIR%\backend.log" 2>&1
echo %date% %time% — Backend started >> "%LOG_DIR%\startup.log"

timeout /t 3 /nobreak >nul

echo.
echo ====================================
echo   Horse Racing Dashboard Started!
echo   Local: http://localhost:8000
echo ====================================
echo.
echo Press Ctrl+C to stop...

REM Keep window open
pause >nul
