@echo off
echo Starting Portable Installation...
echo This will download a standalone Python version so you don't need to install it system-wide.
echo.

powershell -ExecutionPolicy Bypass -File install_portable.ps1

if %errorlevel% neq 0 (
    echo.
    echo Installation Failed!
    pause
    exit /b %errorlevel%
)
echo.
echo Installation Successful! You can now run the app using run.bat.
pause
