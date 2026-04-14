@echo off
if exist "python_embed\python.exe" (
    "python_embed\python.exe" primery_app.py
) else (
    python primery_app.py
)
pause
