param([string]$Image = 'modelbench-coding:1')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
docker build --tag $Image (Join-Path $ProjectRoot 'backend/coding_runner')
if ($LASTEXITCODE -ne 0) { throw 'Coding runner image build failed' }
