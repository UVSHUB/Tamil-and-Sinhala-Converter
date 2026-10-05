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
    echo Please copy '.env.example' to '.env' and put your Google Gemini API key inside it.
    pause
    exit /b
)

echo [1/3] Preparing Python Virtual Environment...
if not exist .venv (
    echo Creating virtual environment and installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    echo Virtual environment ready.
)

echo [2/3] Preparing Frontend Dependencies...
if not exist frontend\node_modules (
    echo Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
) else (
    echo Frontend dependencies ready.
)

echo [3/3] Launching Backend & Frontend Servers...

:: Start backend in a new window (cmd /k keeps window open if any error occurs)
start "SinTam Backend Server (Port 8000)" cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

:: Start frontend in a new window
start "SinTam Frontend Server (Port 5180)" cmd /k "cd frontend && npm run dev"

:: Wait 3 seconds then open browser automatically
timeout /t 3 /nobreak >nul
start http://localhost:5180

echo.
echo ==================================================
echo   Success! Application servers have been launched.
echo   Opening http://localhost:5180 in your browser...
echo.
echo   Keep the server terminal windows open while using the app.
echo ==================================================
echo.
pause
