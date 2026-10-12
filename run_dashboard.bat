@echo off
title BTC Market Intelligence Dashboard Launcher
cd /d "%~dp0"

echo ======================================================================
echo    BTC MARKET INTELLIGENCE V4.1 - QUANT TRADING TERMINAL
echo ======================================================================
echo.

:: 1. Detect Python interpreter (virtualenv priority, then system python)
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
    echo [*] Detected virtual environment: .venv
) else if exist "venv\Scripts\python.exe" (
    set PYTHON_EXE=venv\Scripts\python.exe
    echo [*] Detected virtual environment: venv
) else (
    echo [*] Using system Python from PATH
)

:: 2. Verify Python is reachable
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python interpreter not found!
    echo Please install Python 3.10+ and ensure it is available in PATH.
    pause
    exit /b 1
)

:: 3. Verify critical dashboard packages: streamlit, plotly, pandas
%PYTHON_EXE% -c "import streamlit, plotly, pandas" >nul 2>&1
if errorlevel 1 (
    echo [*] Required dashboard packages are missing.
    echo [*] Installing dependencies from requirements.txt...
    %PYTHON_EXE% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install required packages!
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed successfully.
)

:: 4. Ensure market snapshot exists before running dashboard
if not exist "market_snapshot.json" (
    echo [*] Market snapshot not found. Running fast momentum scan to fetch fresh data...
    %PYTHON_EXE% btc_market_intelligence.py --fast
)

:: 5. Free port 8501 if lingering from a previous Python/Streamlit session
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p.ProcessName -like '*python*') { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }" >nul 2>&1

:: 6. Launch Streamlit Dashboard
echo.
echo [*] Launching Streamlit Dashboard on http://localhost:8501 ...
echo [*] Press CTRL+C in this terminal window to stop the server.
echo.

%PYTHON_EXE% -m streamlit run dashboard.py --server.port=8501 --server.headless=false --browser.gatherUsageStats=false

if errorlevel 1 (
    echo.
    echo [ERROR] Dashboard exited with an error code.
    pause
)
