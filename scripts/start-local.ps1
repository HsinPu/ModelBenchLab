param([int]$FrontendPort = 5173)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run setup commands in README.md first.' }
$logDir = Join-Path $projectRoot 'work'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
foreach ($port in @(8000,$FrontendPort)) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is in use. Stop the existing instance first." }
}
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput "$logDir/api.log" -RedirectStandardError "$logDir/api-error.log" -PassThru
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  try { $null = Invoke-RestMethod 'http://127.0.0.1:8000/api/health'; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ready) { Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue; throw 'API failed to start. Check work/api-error.log.' }
$workerProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','app.execution' -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput "$logDir/worker.log" -RedirectStandardError "$logDir/worker-error.log" -PassThru
$nodeExe = (Get-Command node.exe).Source
$viteEntry = Join-Path $frontendDir 'node_modules/vite/bin/vite.js'
$frontendProcess = Start-Process -FilePath $nodeExe -ArgumentList ('"' + $viteEntry + '"'),'--host','127.0.0.1','--port',([string]$FrontendPort),'--strictPort' -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput "$logDir/frontend.log" -RedirectStandardError "$logDir/frontend-error.log" -PassThru
@{api=$apiProcess.Id;worker=$workerProcess.Id;frontend=$frontendProcess.Id} | ConvertTo-Json | Set-Content "$logDir/processes.json"
Write-Output "ModelBenchLab: http://127.0.0.1:$FrontendPort"
