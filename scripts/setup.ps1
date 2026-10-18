$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path '.venv')) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r services\api\requirements-dev.txt -r services\print-agent\requirements-dev.txt
pnpm install
Write-Host '开发依赖安装完成。复制 .env.example 为 .env 后即可启动。'

