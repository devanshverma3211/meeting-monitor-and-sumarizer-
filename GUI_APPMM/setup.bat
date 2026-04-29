@echo off
setlocal EnableDelayedExpansion
title Meeting Monitor — First-Time Setup
color 0A
cls

echo.
echo  =======================================================
echo    Meeting Monitor — First-Time Setup
echo  =======================================================
echo.
echo  This will:
echo    [1] Check Python is installed
echo    [2] Install all required packages
echo    [3] Create a desktop shortcut with icon
echo.
echo  This only needs to be run ONCE.
echo  -------------------------------------------------------
echo.
pause


:: -------------------------------------------------------
:: STEP 1 — Check Python 3.10+
:: -------------------------------------------------------
echo  [1/4]  Checking Python...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Python was not found on this computer.
    echo.
    echo  Please install Python 3.10 or later from:
    echo    https://python.org/downloads
    echo.
    echo  IMPORTANT: Tick "Add Python to PATH" during install,
    echo  then run this setup again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK]  Python %PYVER% found.
echo.


:: -------------------------------------------------------
:: STEP 2 — Create virtual environment
:: -------------------------------------------------------
echo  [2/4]  Setting up isolated Python environment...
echo.

if not exist "venv\" (
    python -m venv venv
    if errorlevel 1 (
        color 0C
        echo  [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK]  Virtual environment created.
) else (
    echo  [OK]  Virtual environment already exists — skipping.
)
echo.


:: -------------------------------------------------------
:: STEP 3 — Install Python dependencies
:: -------------------------------------------------------
echo  [3/4]  Installing packages (first time may take a few minutes)...
echo.
echo         anthropic, faster-whisper, pystray, Pillow and others...
echo.

venv\Scripts\pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo  [ERROR] Package installation failed.
    echo.
    echo  Possible causes:
    echo    - No internet connection
    echo    - Firewall blocking pip
    echo.
    echo  Try running manually:
    echo    venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo  [OK]  All packages installed.
echo.


:: -------------------------------------------------------
:: STEP 4 — Generate icon + Desktop shortcut
:: -------------------------------------------------------
echo  [4/4]  Creating app icon and desktop shortcut...
echo.

:: Generate icon.ico using Pillow
venv\Scripts\python -c ^
"from PIL import Image, ImageDraw; ^
img = Image.new('RGBA', (256,256), (0,0,0,0)); ^
d = ImageDraw.Draw(img); ^
d.ellipse([0,0,255,255], fill=(26,26,46)); ^
d.ellipse([15,15,240,240], fill=(0,180,90)); ^
d.rounded_rectangle([103,55,153,165], radius=22, fill='white'); ^
d.rectangle([119,165,137,205], fill='white'); ^
d.rounded_rectangle([99,200,157,215], radius=6, fill='white'); ^
d.ellipse([60,130,100,175], outline='white', width=6); ^
d.ellipse([156,130,196,175], outline='white', width=6); ^
d.arc([60,55,196,230], start=0, end=180, fill='white', width=6); ^
img.save('icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)]); ^
print('Icon OK')"

if errorlevel 1 (
    echo  [WARN] Could not generate icon — shortcut will use default icon.
)

:: Get the full path of this folder
set "APPDIR=%~dp0"
:: Remove trailing backslash
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

:: Create desktop shortcut via PowerShell
:: Points directly to pythonw.exe so NO terminal window ever appears
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$s = (New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Meeting Monitor.lnk'); ^
$s.TargetPath   = '%APPDIR%\venv\Scripts\pythonw.exe'; ^
$s.Arguments    = '\""%APPDIR%\gui_app.py"\"'; ^
$s.WorkingDirectory = '%APPDIR%'; ^
$s.IconLocation = '%APPDIR%\icon.ico'; ^
$s.Description  = 'Meeting Monitor — Auto-record and summarise Teams calls'; ^
$s.WindowStyle  = 1; ^
$s.Save()"

if errorlevel 1 (
    color 0C
    echo  [ERROR] Could not create desktop shortcut.
    echo.
    echo  You can still launch the app by double-clicking:
    echo    Start Monitor.bat
    echo.
    pause
    exit /b 1
)

echo  [OK]  Desktop shortcut created: "Meeting Monitor"
echo.


:: -------------------------------------------------------
:: Done
:: -------------------------------------------------------
color 0A
echo.
echo  =======================================================
echo    Setup Complete!
echo  =======================================================
echo.
echo    A "Meeting Monitor" shortcut has been placed
echo    on your Desktop.
echo.
echo    Before first use, open config.json and fill in:
echo      - anthropic_api_key   (from console.anthropic.com)
echo      - email / password    (your Outlook/Gmail details)
echo.
echo    Then just double-click the Desktop icon any time.
echo    No terminal needed!
echo  =======================================================
echo.

:: Offer to open config.json right now
set /p OPENCFG= "  Open config.json now to fill in your details? (Y/N): "
if /i "%OPENCFG%"=="Y" (
    if exist "config.json" (
        start notepad config.json
    ) else (
        copy config.example.json config.json >nul
        start notepad config.json
    )
)

echo.
echo  You can close this window.
echo.
pause
exit /b 0
