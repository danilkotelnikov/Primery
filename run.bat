:<<"::CMDLITERAL"
@ECHO OFF
GOTO :WINDOWS
::CMDLITERAL

# =======================================================
# LINUX / MACOS SCRIPT (Bash)
# =======================================================
APP_NAME="primery"
ENV_NAME="primery"
REQUIREMENTS_FILE="requirements.txt"
OS_TYPE=$(uname -s)

if [ "$OS_TYPE" = "Linux" ]; then
    MINIFORGE_INSTALLER="Miniforge3-Linux-x86_64.sh"
elif [ "$OS_TYPE" = "Darwin" ]; then
    MINIFORGE_INSTALLER="Miniforge3-MacOSX-$(uname -m).sh"
else
    echo "[ERROR] Unsupported OS: $OS_TYPE"
    exit 1
fi

MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/$MINIFORGE_INSTALLER"

# Check common miniforge paths
CONDA_BASE=""
if [ -f "$HOME/miniforge3/bin/conda" ]; then
    CONDA_BASE="$HOME/miniforge3"
elif [ -f "/opt/miniforge3/bin/conda" ]; then
    CONDA_BASE="/opt/miniforge3"
fi

# Install Miniforge if not found
if [ -z "$CONDA_BASE" ]; then
    echo "[INFO] Miniforge not found. Downloading and installing Miniforge3..."
    curl -L -o "$MINIFORGE_INSTALLER" "$MINIFORGE_URL"
    if [ ! -f "$MINIFORGE_INSTALLER" ]; then
        echo "[ERROR] Failed to download Miniforge3 installer."
        exit 1
    fi
    echo "[INFO] Installing Miniforge3 interactively..."
    bash "$MINIFORGE_INSTALLER" -b -p "$HOME/miniforge3"
    CONDA_BASE="$HOME/miniforge3"
    rm "$MINIFORGE_INSTALLER"
fi

# Initialize conda base environment
echo "[INFO] Activating base Conda environment..."
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate base

# Create "primery" environment if it doesn't exist
echo "[INFO] Checking for Conda environment '$ENV_NAME'..."
if ! conda env list | grep -q "$ENV_NAME"; then
    echo "[INFO] Environment '$ENV_NAME' not found. Creating it with Python 3.12..."
    conda create -n "$ENV_NAME" python=3.12 -y
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create environment '$ENV_NAME'."
        exit 1
    fi
fi

# Activate the environment and install dependencies
echo "[INFO] Activating environment '$ENV_NAME'..."
conda activate "$ENV_NAME"

echo "[INFO] Checking and installing dependencies from $REQUIREMENTS_FILE..."
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "[WARNING] $REQUIREMENTS_FILE NOT found. Skipping dependencies installation."
fi

# Launch the app
echo "[INFO] Launching the application..."
python primery_app.py
exit $?

:WINDOWS
REM =======================================================
REM WINDOWS SCRIPT (CMD)
REM =======================================================
setlocal enabledelayedexpansion

REM 1. Define paths and variables
set "APP_NAME=primery"
set "ENV_NAME=primery"
set "REQUIREMENTS_FILE=requirements.txt"
set "MINIFORGE_INSTALLER=Miniforge3-Windows-x86_64.exe"
set "MINIFORGE_URL=https://github.com/conda-forge/miniforge/releases/latest/download/%MINIFORGE_INSTALLER%"

REM Check common miniforge paths
set "CONDA_BASE="
if exist "%USERPROFILE%\miniforge3\Scripts\activate.bat" (
    set "CONDA_BASE=%USERPROFILE%\miniforge3"
) else if exist "%USERPROFILE%\AppData\Local\miniforge3\Scripts\activate.bat" (
    set "CONDA_BASE=%USERPROFILE%\AppData\Local\miniforge3"
) else if exist "C:\ProgramData\miniforge3\Scripts\activate.bat" (
    set "CONDA_BASE=C:\ProgramData\miniforge3"
)

REM 2. Install Miniforge if not found
if "%CONDA_BASE%"=="" (
    echo [INFO] Miniforge not found. Downloading and installing Miniforge3...
    curl -L -o "%MINIFORGE_INSTALLER%" "%MINIFORGE_URL%"
    if not exist "%MINIFORGE_INSTALLER%" (
        echo [ERROR] Failed to download Miniforge3 installer.
        pause
        exit /b 1
    )
    echo [INFO] Installing Miniforge3 silently. This may take a few minutes...
    start /wait "" "%MINIFORGE_INSTALLER%" /InstallationType=JustMe /RegisterPython=0 /S /D=%USERPROFILE%\miniforge3
    set "CONDA_BASE=%USERPROFILE%\miniforge3"
    del "%MINIFORGE_INSTALLER%"
)

REM 3. Initialize conda base environment
echo [INFO] Activating base Conda environment...
call "%CONDA_BASE%\Scripts\activate.bat" base

REM Check if conda command is available
where conda >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Conda initialization failed.
    pause
    exit /b 1
)

REM 4. Create "primery" environment if it doesn't exist
echo [INFO] Checking for Conda environment '%ENV_NAME%'...
conda env list | findstr /C:"%ENV_NAME%" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Environment '%ENV_NAME%' not found. Creating it with Python 3.12...
    call conda create -n "%ENV_NAME%" python=3.12 -y
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create environment '%ENV_NAME%'.
        pause
        exit /b 1
    )
)

REM 5. Activate the environment and install dependencies
echo [INFO] Activating environment '%ENV_NAME%'...
call conda activate "%ENV_NAME%"

echo [INFO] Checking and installing dependencies from %REQUIREMENTS_FILE%...
if exist "%REQUIREMENTS_FILE%" (
    call pip install -r "%REQUIREMENTS_FILE%"
) else (
    echo [WARNING] %REQUIREMENTS_FILE% NOT found. Skipping dependencies installation.
)

REM 6. Create Desktop Shortcut icon
if not exist "assets\Logo.ico" (
    python -c "try: from PIL import Image; Image.open('assets/Logo.png').save('assets/Logo.ico'); print('Icon generated'); except Exception as e: pass"
)
set "SHORTCUT_PATH=%UserProfile%\Desktop\Primery.lnk"
set "ICON_PATH=%~dp0assets\Logo.ico"
if not exist "%SHORTCUT_PATH%" (
    echo [INFO] Creating Desktop Shortcut...
    powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%~dp0run.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%ICON_PATH%'; $s.Save()"
)

REM 7. Launch the app
echo [INFO] Launching the application...
start "" pythonw primery_app.py

endlocal
