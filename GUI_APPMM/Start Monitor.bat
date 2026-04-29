@echo off
:: Meeting Monitor — Silent launcher (no terminal window)
:: Double-click this, or use the Desktop shortcut created by setup.bat

cd /d "%~dp0"

:: Guard: if venv doesn't exist, tell user to run setup first
if not exist "venv\Scripts\pythonw.exe" (
    echo.
    echo  Meeting Monitor is not set up yet.
    echo.
    echo  Please double-click  setup.bat  first.
    echo  It takes about 2-3 minutes and only needs to be done once.
    echo.
    pause
    exit /b 1
)

:: Launch GUI silently — no terminal window
start "" "venv\Scripts\pythonw.exe" gui_app.py
