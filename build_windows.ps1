$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($env:OS -ne 'Windows_NT') {
    throw 'Build this bundle on Windows 10/11 64-bit. PyInstaller does not cross-compile Windows COM executables from Linux.'
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'The target ETABS installation is 64-bit; build on 64-bit Windows.'
}

$Venv = Join-Path $Root '.venv-build'
$Python = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Python)) {
    py -3.11 -m venv $Venv
}
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-build.txt
$PythonBits = & $Python -c "import struct; print(struct.calcsize('P') * 8)"
if ($PythonBits.Trim() -ne '64') {
    throw 'Use 64-bit Python 3.11 to build the package for ETABS Ultimate 20.3.0 64-bit.'
}

Remove-Item (Join-Path $Root 'build') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Root 'dist') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Root 'release\ElementSelector') -Recurse -Force -ErrorAction SilentlyContinue

& $Python -m PyInstaller --noconfirm --clean --onedir --console --name ElementSelector `
    --collect-all streamlit --collect-all pandas --collect-all plotly `
    --hidden-import etabs_bridge_client --hidden-import requests `
    --add-data "app.py;." run_app.py

& $Python -m PyInstaller --noconfirm --clean --onedir --console --name EtabsBridge `
    --collect-all comtypes --hidden-import comtypes.client --hidden-import fastapi --hidden-import uvicorn --hidden-import bridge `
    run_bridge.py

& $Python -m PyInstaller --noconfirm --clean --onedir --console --name DebugReport `
    --collect-all comtypes --hidden-import comtypes.client --hidden-import etabs_client `
    run_debug_report.py

$Bundle = Join-Path $Root 'release\ElementSelector'
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null
Copy-Item (Join-Path $Root 'dist\ElementSelector') $Bundle -Recurse
Copy-Item (Join-Path $Root 'dist\EtabsBridge') $Bundle -Recurse
Copy-Item (Join-Path $Root 'dist\DebugReport') $Bundle -Recurse
Copy-Item (Join-Path $Root 'start.bat') $Bundle
Copy-Item (Join-Path $Root 'stop.bat') $Bundle
Copy-Item (Join-Path $Root 'DEBUG_REPORT.py') $Bundle
Copy-Item (Join-Path $Root 'etabs_client.py') $Bundle
Copy-Item (Join-Path $Root 'README_ETABS.md') $Bundle
Copy-Item (Join-Path $Root 'requirements.txt') $Bundle
Copy-Item (Join-Path $Root 'requirements-build.txt') $Bundle

$ZipPath = Join-Path $Root 'ElementSelector-Windows.zip'
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $Bundle '*') -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Build complete: $ZipPath"
Write-Host 'Target: ETABS Ultimate 20.3.0 Build 2929, Windows 10 64-bit.'
Write-Host 'Before sharing, test with the real ETABS model and review the untested API limitations in README_ETABS.md.'
