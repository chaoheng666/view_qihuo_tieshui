@echo off
setlocal

cd /d "%~dp0"
title Futures Premium Dashboard

set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    py -3.11 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

echo.
echo ==========================================
echo   Futures Premium Dashboard
echo ==========================================
echo.

echo [1/3] Check Python...
if not defined PYTHON_CMD (
    echo [ERROR] Python 3.9+ was not found.
    echo Install Python first, then run this script again.
    pause
    exit /b 1
)

call %PYTHON_CMD% --version
if errorlevel 1 (
    echo [ERROR] Python failed to start.
    pause
    exit /b 1
)

echo [2/3] Check dependencies...
call %PYTHON_CMD% -m pip show akshare >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing requirements...
    call %PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements.
        echo Try this manually:
        echo   %PYTHON_CMD% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [3/3] Start web server...
echo.
echo ==========================================
echo   Open this address in your browser:
echo   http://127.0.0.1:5005
echo ==========================================
echo.

start "" http://127.0.0.1:5005
call %PYTHON_CMD% "%~dp0main.py" --web --port 5005

pause
endlocal
