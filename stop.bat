@echo off
setlocal
set "APP_DIR=%~dp0release\ElementSelector"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$dir='%APP_DIR%'; foreach($f in @('app.pid','bridge.pid')){ $path=Join-Path $dir $f; if(Test-Path $path){ $raw=Get-Content $path -ErrorAction SilentlyContinue; $id=0; if([int]::TryParse($raw,[ref]$id)){ $p=Get-Process -Id $id -ErrorAction SilentlyContinue; if($p -and $p.ProcessName -in @('ElementSelector','EtabsBridge')){ Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }; Remove-Item $path -Force -ErrorAction SilentlyContinue } }"
echo Element Selector and its bridge have been stopped if they were running.
endlocal
