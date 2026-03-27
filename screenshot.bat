@echo off
:: CLI drag-and-drop wrapper.
:: Usage: drag an HTML file onto this .bat, or run:
::        screenshot.bat "C:\path\file.html" output.png
::        screenshot.bat "https://example.com" output.png [--width 1440]
::
:: If no output argument is given, saves as screenshot.png in the current folder.

call venv\Scripts\activate

if "%~2"=="" (
    set OUTPUT=screenshot.png
) else (
    set OUTPUT=%~2
)

htmlrf-screenshot %1 -o "%OUTPUT%" %3 %4 %5
echo.
pause
