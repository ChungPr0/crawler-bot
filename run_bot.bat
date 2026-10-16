@echo off
title Hanoi IT Job Radar Bot

if exist venv\Scripts\python.exe goto :run_bot

echo ========================================================
echo   FIRST TIME SETUP: INITIALIZING ENVIRONMENT
echo ========================================================

python --version >nul 2>&1
if errorlevel 1 goto :no_python

echo [1/3] Creating virtual environment...
python -m venv venv

echo [2/3] Installing Python dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\pip.exe install -r requirements.txt

echo [3/3] Installing Playwright Chromium browser...
venv\Scripts\playwright.exe install chromium

if not exist .env copy .env.example .env

:run_bot
echo ========================================================
echo   HANOI IT JOB RADAR BOT IS RUNNING
echo   Press Ctrl + C to stop the bot anytime
echo ========================================================
echo.

venv\Scripts\python.exe main.py
pause
exit /b 0

:no_python
echo [ERROR] Python not found on your system!
echo Please install Python using: winget install Python.Python.3.11
pause
exit /b 1
