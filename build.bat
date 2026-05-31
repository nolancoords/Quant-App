@echo off
setlocal enabledelayedexpansion
title quantsim launcher

echo.
echo  ================================================
echo   quantsim dashboard launcher
echo  ================================================
echo.

:: ── locate Python ────────────────────────────────────────────────────────────
set PYTHON=
for %%p in (python python3) do (
    if "!PYTHON!"=="" (
        where %%p >nul 2>&1 && set PYTHON=%%p
    )
)
if "!PYTHON!"=="" (
    echo  [ERROR] Python not found. Install Python 3.9+ and add it to PATH.
    pause & exit /b 1
)
echo  [ok] Python  : !PYTHON!

:: ── locate Node / npm ────────────────────────────────────────────────────────
where npm >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] npm not found. Install Node.js 18+ and add it to PATH.
    pause & exit /b 1
)
echo  [ok] npm     : found

:: ── resolve script directory (works from any cwd) ────────────────────────────
set ROOT=%~dp0
set BACK=%ROOT%backend
set FRONT=%ROOT%frontend

:: ── install Python deps ───────────────────────────────────────────────────────
echo.
echo  [1/3] installing Python dependencies...
!PYTHON! -m pip install -q -r "%BACK%\requirements.txt"
if errorlevel 1 (
    echo  [ERROR] pip install failed. Check requirements.txt and your Python env.
    pause & exit /b 1
)
echo  [ok] Python deps installed

:: ── install Node deps (only if node_modules absent) ──────────────────────────
echo.
echo  [2/3] installing Node dependencies...
if not exist "%FRONT%\node_modules" (
    pushd "%FRONT%"
    npm install --silent
    if errorlevel 1 (
        echo  [ERROR] npm install failed.
        popd & pause & exit /b 1
    )
    popd
    echo  [ok] Node deps installed
) else (
    echo  [ok] node_modules already present, skipping
)

:: ── launch backend in its own window ─────────────────────────────────────────
echo.
echo  [3/3] starting servers...
start "quantsim backend :8000" cmd /k "cd /d "%BACK%" && echo. && echo  Flask backend starting on http://localhost:8000 && echo. && !PYTHON! app.py"

:: small pause so Flask has a moment to bind before the browser opens
timeout /t 2 /nobreak >nul

:: ── launch frontend in its own window ────────────────────────────────────────
start "quantsim frontend :5173" cmd /k "cd /d "%FRONT%" && echo. && echo  Vite dev server starting on http://localhost:5173 && echo. && npm run dev"

:: ── open browser after a short delay ─────────────────────────────────────────
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo  ================================================
echo   both servers are running in separate windows
echo   frontend  : http://localhost:5173
echo   backend   : http://localhost:8000
echo.
echo   close those two windows to stop the servers
echo  ================================================
echo.
pause
