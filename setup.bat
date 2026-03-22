@echo off
echo ============================================================
echo  HTML RenderFriend — One-click setup
echo ============================================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org and add to PATH.
    pause & exit /b 1
)

:: Create virtual environment if it doesn't already exist
if not exist venv\ (
    echo [1/4] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/4] Virtual environment already exists — skipping.
)

:: Activate venv
call venv\Scripts\activate

:: Install Python dependencies
echo [2/4] Installing Python packages...
pip install --quiet -r requirements.txt

:: Install Playwright's Chromium browser
echo [3/4] Installing Playwright Chromium browser...
playwright install chromium

echo.
echo [4/4] Done!  Run the app with one of:
echo.
echo        screenshot.bat "https://example.com" out.png     (CLI)
echo        python screenshot.py --help                      (CLI help)
echo        gui.bat                                           (GUI)
echo.
pause
