@echo off
title SinTam Voice Translator Launcher
echo ==================================================
echo   Welcome to the SinTam Voice Translator!
echo ==================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed. Please install Python from https://www.python.org/downloads/
    pause
    exit /b
)

:: Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed. Please install Node.js from https://nodejs.org/
    pause
    exit /b
)

:: Check for API key in .env
if not exist .env (
    echo [ERROR] Configuration file missing! 
    echo Please rename '.env.example' to '.env' and put your Google Gemini API key inside it.
    pause
    exit /b
)

echo [1/3] Preparing the Background AI Engine (This might take a minute the first time)...
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing AI dependencies...
pip install -r requirements.txt >nul 2>&1

echo [2/3] Preparing the User Interface...
cd frontend
call npm install >nul 2>&1
cd ..

echo [3/3] Launching the application...
:: Start backend in a new minimized window
start "SinTam Backend Server (Do Not Close)" /MIN cmd /c "call .venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000"

:: Start frontend in a new minimized window
start "SinTam Frontend Server (Do Not Close)" /MIN cmd /c "cd frontend && npm run dev"

echo.
echo ==================================================
echo   Success! The application servers are starting.
echo.
echo   Your browser should open automatically in a moment.
echo   If it doesn't, manually go to: http://localhost:5173
echo.
echo   NOTE: Two minimized black windows have been opened 
echo   for the servers. Leave them running while you use 
echo   the app. Close them when you are done.
echo ==================================================
echo.
pause
