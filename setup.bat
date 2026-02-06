@echo off
title ComfyUI-VastAI Setup
cls
echo ========================================================
echo       ComfyUI-VastAI Configurator for Windows
echo ========================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+
    pause
    exit /b
)

echo [1/3] Installing Dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b
)

echo [2/3] Checking Vast.ai CLI...
vastai --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Vast.ai CLI not found even after install.
    pause
    exit /b
)

echo.
echo ========================================================
echo [3/3] Configuration
echo ========================================================
echo.
echo Please enter your keys below. Press Enter to skip if already set.
echo.

set /p VAST_API_KEY="Enter Vast.ai API Key: "
if not "%VAST_API_KEY%"=="" (
    vastai set api-key %VAST_API_KEY%
    echo [OK] API Key set.
)

echo.
echo Setup Complete!
echo.
echo To run a workflow:
echo python vastai_runner.py --workflow your_workflow.json
echo.
pause
