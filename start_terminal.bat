@echo off
title BTC Market Intelligence v5.0 - Institutional Trading Terminal
cd /d "%~dp0"

echo ======================================================================
echo    BTC MARKET INTELLIGENCE TERMINAL v5.0 (PRO BLOOMBERG EDITION)
echo ======================================================================
echo.

:: 1. Detect Python interpreter
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
    echo [*] Active environment: .venv
) else if exist "venv\Scripts\python.exe" (
    set PYTHON_EXE=venv\Scripts\python.exe
    echo [*] Active environment: venv
) else (
    echo [*] Active environment: System Python
)

:: 2. Verify Python
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in environment or PATH!
    pause
    exit /b 1
)

:: 3. Free port 8501 if occupied from a previous session
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p.ProcessName -like '*python*') { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }" >nul 2>&1

:: 4. Start Autonomous Background Daemon
echo [*] Launching Autonomous Background Engine (daemon_engine.py)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*daemon_engine.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
start "BTC Data Daemon" /min %PYTHON_EXE% daemon_engine.py --interval 20

:: 5. Initial sync
echo [*] Synchronizing live exchange feeds...
%PYTHON_EXE% daemon_engine.py --once

:: 6. Launch Web Terminal
echo.
echo ======================================================================
echo    WEB TERMINAL ACTIVE: http://localhost:8501
echo    Autonomous daemon is streaming telemetry every 20 seconds.
echo    Press CTRL+C to terminate terminal and background services.
echo ======================================================================
echo.

%PYTHON_EXE% -m streamlit run dashboard.py --server.port=8501 --server.headless=false --browser.gatherUsageStats=false

:: 7. Cleanup on exit
echo.
echo [*] Stopping background daemon...
%PYTHON_EXE% daemon_engine.py --stop
