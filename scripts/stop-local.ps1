$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'work/processes.json'
if (Test-Path -LiteralPath $pidFile) {
  $processIds = Get-Content -LiteralPath $pidFile | ConvertFrom-Json
  foreach ($processId in @($processIds.api,$processIds.worker,$processIds.frontend)) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($processInfo -and (($processInfo.ExecutablePath -and $processInfo.ExecutablePath.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) -or ($processInfo.CommandLine -and $processInfo.CommandLine.Contains($projectRoot)))) { Stop-Process -Id $processId }
  }
  Remove-Item -LiteralPath $pidFile
}
