$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$api = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--reload','--app-dir','services/api' -PassThru -WindowStyle Hidden
$agent = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--reload','--port','17321','--app-dir','services/print-agent' -PassThru -WindowStyle Hidden
try { pnpm dev } finally { Stop-Process -Id $api.Id,$agent.Id -ErrorAction SilentlyContinue }

