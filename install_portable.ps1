# PowerShell script to install portable Python and dependencies

$ErrorActionPreference = "Stop"
$pythonVersion = "3.10.11"
$pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
$zipPath = "python_embed.zip"
$destDir = "python_embed"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipPath = "get-pip.py"

Write-Host "Checking for existing installation..."
if (Test-Path "$destDir\python.exe") {
    Write-Host "Run 'clean_install.bat' first if you want to reinstall."
    Write-Host "Portable Python found. Attempting to install requirements..."
    & "$destDir\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Success!"
        exit 0
    }
}

Write-Host "Downloading Python $pythonVersion Embeddable..."
Invoke-WebRequest -Uri $pythonUrl -OutFile $zipPath

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $destDir -Force

# Enable 'site' package to allow pip execution
Write-Host "Configuring python._pth..."
$pthFile = Get-ChildItem -Path $destDir -Filter "*._pth" | Select-Object -First 1
if ($pthFile) {
    $content = Get-Content $pthFile.FullName
    $content = $content -replace "#import site", "import site"
    Set-Content $pthFile.FullName $content
}

Write-Host "Downloading get-pip.py..."
Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath

Write-Host "Installing pip..."
& "$destDir\python.exe" $getPipPath --no-warn-script-location

Write-Host "Installing dependencies from requirements.txt..."
& "$destDir\python.exe" -m pip install -r requirements.txt --no-warn-script-location

# Cleanup
Write-Host "Cleaning up temporary files..."
Remove-Item $zipPath -ErrorAction SilentlyContinue
Remove-Item $getPipPath -ErrorAction SilentlyContinue

Write-Host "Portable installation complete!"
