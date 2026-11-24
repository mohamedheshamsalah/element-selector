@echo off
setlocal
cd /d "%~dp0"
set "MOCK=0"
set "APP_DIR=%~dp0release\ElementSelector"
if not exist "%APP_DIR%\ElementSelector\ElementSelector.exe" (
  echo Packaged app not found. Run build_windows.ps1 first.
  pause
  exit /b 1
)
if not exist "%APP_DIR%\EtabsBridge\EtabsBridge.exe" (
  echo Packaged ETABS bridge not found. Run build_windows.ps1 first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '%APP_DIR%\EtabsBridge\EtabsBridge.exe' -WorkingDirectory '%APP_DIR%' -PassThru; Set-Content -Path '%APP_DIR%\bridge.pid' -Value $p.Id"
if errorlevel 1 (
  echo Could not start the ETABS bridge.
  pause
  exit /b 1
)

echo Waiting for the local bridge...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 30;$i++){ try { $r=Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 1; if($r.ok){$ok=$true;break} } catch{}; Start-Sleep -Seconds 1 }; if(-not $ok){exit 1}"
if errorlevel 1 (
  echo Bridge did not become ready. Check antivirus and try stop.bat before retrying.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '%APP_DIR%\ElementSelector\ElementSelector.exe' -WorkingDirectory '%APP_DIR%' -PassThru; Set-Content -Path '%APP_DIR%\app.pid' -Value $p.Id"
if errorlevel 1 (
  echo Could not start Element Selector.
  pause
  exit /b 1
)
timeout /t 5 /nobreak >nul
start "Element Selector" "http://127.0.0.1:8501"
echo Element Selector is running locally. Use stop.bat when finished.
endlocal
