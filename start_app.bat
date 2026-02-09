@echo off
title ComfyUI-VastAI Desktop
cls
echo Starting Launcher...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Please install Python 3.10+
    pause
    exit /b
)

echo Checking dependencies...
pip install -r requirements.txt --quiet

echo Launching App...
python launcher.py
pause
