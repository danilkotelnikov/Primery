@echo off
echo Cleaning up portable installation...
if exist "python_embed" (
    rmdir /s /q "python_embed"
    echo Removed python_embed directory.
)
if exist "python_embed.zip" (
    del "python_embed.zip"
    echo Removed python_embed.zip.
)
if exist "get-pip.py" (
    del "get-pip.py"
    echo Removed get-pip.py.
)
echo.
echo Cleanup complete. You can try running install.bat again.
pause
